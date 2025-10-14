#!/usr/bin/env python3
"""
Example client for exercising the StreamMessage RPC exposed by grpc_server.py.

Run this script while the gRPC server is live. It sends a message, prints the
streamed chunks, and preserves the session ID so you can continue the same
conversation on subsequent calls.
"""

import argparse
import sys

import grpc

import travel_chat_pb2 as chat_pb2
import travel_chat_pb2_grpc as chat_pb2_grpc


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream chat replies from the travel assistant gRPC service.")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost; use tunnel host for VS Code)")
    parser.add_argument("--port", type=int, default=50051, help="Server port (default: 50051; use tunnel port, often 443)")
    parser.add_argument("--session-id", default="", help="Existing session ID; leave blank for a new conversation")
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional initial message to send before entering interactive mode.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Use an insecure (plaintext) channel even if the port suggests TLS.",
    )
    args = parser.parse_args()

    target = f"{args.host}:{args.port}"
    if args.insecure:
        channel = grpc.insecure_channel(target)
    else:
        # Default to secure channel; useful for VS Code / dev tunnels that expose HTTPS endpoints.
        channel = grpc.secure_channel(target, grpc.ssl_channel_credentials())
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
    except grpc.FutureTimeoutError:
        print(f"Unable to connect to gRPC server at {target}. Is it running?", file=sys.stderr)
        sys.exit(1)

    stub = chat_pb2_grpc.TravelChatServiceStub(channel)

    session_id = args.session_id

    def send_message(message: str) -> str:
        nonlocal session_id
        request = chat_pb2.ChatRequest(session_id=session_id, message=message)
        print(f"\n→ You: {message}")
        for chunk in stub.StreamMessage(request):
            session_id = chunk.session_id or session_id
            print(f"← Assistant: {chunk.content}")
            if chunk.is_final:
                break
        return session_id

    # Optional initial prompt
    if args.prompt:
        send_message(args.prompt)

    # Interactive loop
    try:
        while True:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "bye"}:
                print("Goodbye!")
                break
            send_message(user_input)
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
