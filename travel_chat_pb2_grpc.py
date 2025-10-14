"""gRPC plumbing for the travel chat service."""

import grpc

import travel_chat_pb2 as travel__chat__pb2


class TravelChatServiceStub(object):
    """Client stub for the TravelChatService."""

    def __init__(self, channel: grpc.Channel) -> None:
        self.SendMessage = channel.unary_unary(
            "/travelagent.TravelChatService/SendMessage",
            request_serializer=travel__chat__pb2.ChatRequest.SerializeToString,
            response_deserializer=travel__chat__pb2.ChatReply.FromString,
        )
        self.StreamMessage = channel.unary_stream(
            "/travelagent.TravelChatService/StreamMessage",
            request_serializer=travel__chat__pb2.ChatRequest.SerializeToString,
            response_deserializer=travel__chat__pb2.ChatChunk.FromString,
        )


class TravelChatServiceServicer(object):
    """Base servicer to be extended with application logic."""

    def SendMessage(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("SendMessage is not implemented")

    def StreamMessage(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("StreamMessage is not implemented")


def add_TravelChatServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
        "SendMessage": grpc.unary_unary_rpc_method_handler(
            servicer.SendMessage,
            request_deserializer=travel__chat__pb2.ChatRequest.FromString,
            response_serializer=travel__chat__pb2.ChatReply.SerializeToString,
        ),
        "StreamMessage": grpc.unary_stream_rpc_method_handler(
            servicer.StreamMessage,
            request_deserializer=travel__chat__pb2.ChatRequest.FromString,
            response_serializer=travel__chat__pb2.ChatChunk.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "travelagent.TravelChatService", rpc_method_handlers
    )
    server.add_generic_rpc_handlers((generic_handler,))


class TravelChatService(object):
    """Convenience mixin exposing helpers for dynamic routing."""

    @staticmethod
    def add_to_server(servicer, server):
        add_TravelChatServiceServicer_to_server(servicer, server)
