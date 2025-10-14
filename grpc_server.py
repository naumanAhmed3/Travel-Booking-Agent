#!/usr/bin/env python3
"""
gRPC server for the conversational travel assistant.

Each connected client provides a session ID (or receives a new one) so the
conversation state remains isolated per user across multiple requests.
"""

import argparse
import asyncio
import logging
import os
import signal
import uuid
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import grpc

import travel_chat_pb2 as chat_pb2
import travel_chat_pb2_grpc as chat_pb2_grpc
from travel_agent import ConversationalTravelAgent


@dataclass
class SessionState:
    agent: ConversationalTravelAgent
    lock: asyncio.Lock
    last_seen: float


class SessionManager:
    """Keeps per-user ConversationalTravelAgent instances alive with TTL pruning."""

    def __init__(self, ttl_seconds: float = 1800.0) -> None:
        self._ttl = ttl_seconds
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, session_id: Optional[str]) -> Tuple[str, SessionState]:
        """Return an active session, creating one if necessary."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()

            # Drop expired sessions
            expired = [
                sid
                for sid, state in self._sessions.items()
                if now - state.last_seen > self._ttl
            ]
            for sid in expired:
                logging.debug("Expiring session %s", sid)
                del self._sessions[sid]

            # Create a new session if missing
            if not session_id or session_id not in self._sessions:
                session_id = session_id or uuid.uuid4().hex
                agent = ConversationalTravelAgent()
                self._sessions[session_id] = SessionState(
                    agent=agent, lock=asyncio.Lock(), last_seen=now
                )
                logging.info("Created new session %s", session_id)
            else:
                self._sessions[session_id].last_seen = now

            return session_id, self._sessions[session_id]


class TravelChatService(chat_pb2_grpc.TravelChatServiceServicer):
    """Implements the gRPC service backed by ConversationalTravelAgent instances."""

    def __init__(self, session_manager: SessionManager) -> None:
        self._sessions = session_manager

    async def SendMessage(self, request, context):  # type: ignore[override]
        session_id, state = await self._sessions.acquire(
            request.session_id.strip() or None
        )
        loop = asyncio.get_running_loop()

        async with state.lock:
            try:
                result = await loop.run_in_executor(
                    None, state.agent.process_user_input_conversationally, request.message
                )
            except Exception as exc:  # pragma: no cover - defensive
                logging.exception(
                    "Failed to process message for session %s", session_id
                )
                context.set_details(f"processing error: {exc}")
                context.set_code(grpc.StatusCode.INTERNAL)
                return chat_pb2.ChatReply(
                    session_id=session_id,
                    reply="Sorry, something went wrong while processing your request.",
                )

        reply_text = result.get("response", "")
        missing_info = [str(item) for item in (result.get("missing_info") or [])]
        booking_context = state.agent.current_booking_info.copy()
        booking_map = {
            key: str(value)
            for key, value in booking_context.items()
            if value not in (None, "")
        }

        return chat_pb2.ChatReply(
            session_id=session_id,
            reply=reply_text,
            booking_info=booking_map,
            missing_info=missing_info,
        )

    async def StreamMessage(self, request, context):  # type: ignore[override]
        session_id, state = await self._sessions.acquire(
            request.session_id.strip() or None
        )
        loop = asyncio.get_running_loop()

        async with state.lock:
            try:
                result = await loop.run_in_executor(
                    None, state.agent.process_user_input_conversationally, request.message
                )
            except Exception as exc:  # pragma: no cover - defensive
                logging.exception(
                    "Failed to process message for session %s", session_id
                )
                await context.abort(
                    grpc.StatusCode.INTERNAL, f"processing error: {exc}"
                )
            else:
                reply_text = result.get("response", "")

        yield chat_pb2.ChatChunk(
            session_id=session_id,
            content=reply_text,
            is_final=True,
        )


async def serve(host: str, port: int, ttl_seconds: float) -> None:
    server = grpc.aio.server()
    session_manager = SessionManager(ttl_seconds=ttl_seconds)
    chat_service = TravelChatService(session_manager)
    chat_pb2_grpc.add_TravelChatServiceServicer_to_server(chat_service, server)

    listen_addr = f"{host}:{port}"
    server.add_insecure_port(listen_addr)
    await server.start()
    logging.info("Travel chat gRPC server listening on %s", listen_addr)

    # Graceful shutdown on signals
    shutdown_event = asyncio.Event()

    def _handle_signal(*_args):
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, lambda *_: shutdown_event.set())

    await shutdown_event.wait()
    logging.info("Shutting down gRPC server...")
    await server.stop(grace=5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the travel assistant gRPC server."
    )
    parser.add_argument(
        "--host",
        default=os.getenv("GRPC_HOST", "0.0.0.0"),
        help="Host interface to bind (default: 0.0.0.0 or GRPC_HOST env).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("GRPC_PORT", "50051")),
        help="Port to listen on (default: 50051 or GRPC_PORT env).",
    )
    parser.add_argument(
        "--session-ttl",
        type=int,
        default=int(os.getenv("GRPC_SESSION_TTL", "1800")),
        help="Seconds to keep an idle conversation alive (default: 1800).",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = parse_args()
    asyncio.run(serve(args.host, args.port, float(args.session_ttl)))


if __name__ == "__main__":
    main()
