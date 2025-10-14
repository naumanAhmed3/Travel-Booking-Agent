# Generated support classes for travel chat gRPC service without using protoc.
# This module programmatically assembles the descriptor metadata so that the
# repository does not rely on pre-generated artifacts.

from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pb2 as _descriptor_pb2
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database

_sym_db = _symbol_database.Default()

_FILE_DESCRIPTOR_PROTO = _descriptor_pb2.FileDescriptorProto()
_FILE_DESCRIPTOR_PROTO.name = "travel_chat.proto"
_FILE_DESCRIPTOR_PROTO.package = "travelagent"
_FILE_DESCRIPTOR_PROTO.syntax = "proto3"

# ChatRequest
_chat_request = _FILE_DESCRIPTOR_PROTO.message_type.add()
_chat_request.name = "ChatRequest"
field = _chat_request.field.add()
field.name = "session_id"
field.number = 1
field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
field.type = _descriptor.FieldDescriptor.TYPE_STRING
field = _chat_request.field.add()
field.name = "message"
field.number = 2
field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
field.type = _descriptor.FieldDescriptor.TYPE_STRING

# ChatReply
_chat_reply = _FILE_DESCRIPTOR_PROTO.message_type.add()
_chat_reply.name = "ChatReply"
field = _chat_reply.field.add()
field.name = "session_id"
field.number = 1
field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
field.type = _descriptor.FieldDescriptor.TYPE_STRING
field = _chat_reply.field.add()
field.name = "reply"
field.number = 2
field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
field.type = _descriptor.FieldDescriptor.TYPE_STRING

# BookingInfo map entry
_booking_entry = _chat_reply.nested_type.add()
_booking_entry.name = "BookingInfoEntry"
_booking_entry.options.map_entry = True
bk_field = _booking_entry.field.add()
bk_field.name = "key"
bk_field.number = 1
bk_field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
bk_field.type = _descriptor.FieldDescriptor.TYPE_STRING
bk_field = _booking_entry.field.add()
bk_field.name = "value"
bk_field.number = 2
bk_field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
bk_field.type = _descriptor.FieldDescriptor.TYPE_STRING

field = _chat_reply.field.add()
field.name = "booking_info"
field.number = 3
field.label = _descriptor.FieldDescriptor.LABEL_REPEATED
field.type = _descriptor.FieldDescriptor.TYPE_MESSAGE
field.type_name = ".travelagent.ChatReply.BookingInfoEntry"

field = _chat_reply.field.add()
field.name = "missing_info"
field.number = 4
field.label = _descriptor.FieldDescriptor.LABEL_REPEATED
field.type = _descriptor.FieldDescriptor.TYPE_STRING

# ChatChunk for streaming responses
_chat_chunk = _FILE_DESCRIPTOR_PROTO.message_type.add()
_chat_chunk.name = "ChatChunk"
field = _chat_chunk.field.add()
field.name = "session_id"
field.number = 1
field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
field.type = _descriptor.FieldDescriptor.TYPE_STRING
field = _chat_chunk.field.add()
field.name = "content"
field.number = 2
field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
field.type = _descriptor.FieldDescriptor.TYPE_STRING
field = _chat_chunk.field.add()
field.name = "is_final"
field.number = 3
field.label = _descriptor.FieldDescriptor.LABEL_OPTIONAL
field.type = _descriptor.FieldDescriptor.TYPE_BOOL

# Service definition
_service = _FILE_DESCRIPTOR_PROTO.service.add()
_service.name = "TravelChatService"

method = _service.method.add()
method.name = "SendMessage"
method.input_type = ".travelagent.ChatRequest"
method.output_type = ".travelagent.ChatReply"

method = _service.method.add()
method.name = "StreamMessage"
method.input_type = ".travelagent.ChatRequest"
method.output_type = ".travelagent.ChatChunk"
method.server_streaming = True

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    _FILE_DESCRIPTOR_PROTO.SerializeToString()
)

_CHATREQUEST = DESCRIPTOR.message_types_by_name["ChatRequest"]
_CHATREPLY = DESCRIPTOR.message_types_by_name["ChatReply"]
_CHATCHUNK = DESCRIPTOR.message_types_by_name["ChatChunk"]
_CHATREPLY_BOOKINGINFOENTRY = _CHATREPLY.nested_types_by_name["BookingInfoEntry"]


class ChatRequest(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = _CHATREQUEST
    __module__ = __name__


_sym_db.RegisterMessage(ChatRequest)


class ChatReply_BookingInfoEntry(
    _message.Message, metaclass=_reflection.GeneratedProtocolMessageType
):
    DESCRIPTOR = _CHATREPLY_BOOKINGINFOENTRY
    __module__ = __name__


_sym_db.RegisterMessage(ChatReply_BookingInfoEntry)


class ChatReply(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = _CHATREPLY
    __module__ = __name__


_sym_db.RegisterMessage(ChatReply)


class ChatChunk(_message.Message, metaclass=_reflection.GeneratedProtocolMessageType):
    DESCRIPTOR = _CHATCHUNK
    __module__ = __name__


_sym_db.RegisterMessage(ChatChunk)

__all__ = [
    "ChatRequest",
    "ChatReply",
    "ChatReply_BookingInfoEntry",
    "ChatChunk",
]
