"""Constants for Matrix Extended."""

from typing import Final

DOMAIN: Final = "matrix_extended"

CONF_HOMESERVER: Final = "homeserver"
CONF_USER_ID: Final = "user_id"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEFAULT_ROOM: Final = "default_room"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_REQUIRE_E2EE: Final = "require_e2ee"
CONF_STORE_KEY: Final = "store_key"
CONF_INCOMING_ENABLED: Final = "incoming_enabled"
CONF_ALLOWED_USERS: Final = "allowed_users"
CONF_ALLOWED_ROOMS: Final = "allowed_rooms"
CONF_DOWNLOAD_INCOMING_MEDIA: Final = "download_incoming_media"
CONF_INCOMING_MEDIA_RETENTION_DAYS: Final = "incoming_media_retention_days"
CONF_INCOMING_MEDIA_MAX_MB: Final = "incoming_media_max_mb"
CONF_ROUTING_PROFILES: Final = "routing_profiles"
CONF_VOICE_ASSIST_ENABLED: Final = "voice_assist_enabled"
CONF_VOICE_ASSIST_STT_ENTITY: Final = "voice_assist_stt_entity"
CONF_VOICE_ASSIST_LANGUAGE: Final = "voice_assist_language"
CONF_VOICE_ASSIST_CONVERSATION_AGENT: Final = "voice_assist_conversation_agent"
CONF_VOICE_ASSIST_REPLY_MODE: Final = "voice_assist_reply_mode"
CONF_VOICE_ASSIST_TTS_ENTITY: Final = "voice_assist_tts_entity"
CONF_VOICE_ASSIST_ALLOWED_USERS: Final = "voice_assist_allowed_users"
CONF_VOICE_ASSIST_ALLOWED_ROOMS: Final = "voice_assist_allowed_rooms"

DEFAULT_INCOMING_MEDIA_RETENTION_DAYS: Final = 7
DEFAULT_INCOMING_MEDIA_MAX_MB: Final = 256

SERVICE_SEND: Final = "send"
SERVICE_SEND_VOICE: Final = "send_voice"
SERVICE_TRANSCRIBE_VOICE: Final = "transcribe_voice"
SERVICE_SEND_LOCATION: Final = "send_location"
SERVICE_REPLY: Final = "reply"
SERVICE_REACT: Final = "react"
SERVICE_EDIT: Final = "edit"
SERVICE_REDACT: Final = "redact"
SERVICE_PURGE_MEDIA: Final = "purge_media"
SERVICE_REGISTER_COMMAND: Final = "register_command"
SERVICE_UNREGISTER_COMMAND: Final = "unregister_command"
ATTR_ACCOUNT: Final = "account"
ATTR_TARGET: Final = "target"
ATTR_MESSAGE: Final = "message"
ATTR_FORMAT: Final = "format"
ATTR_MSGTYPE: Final = "msgtype"
ATTR_MENTION_USERS: Final = "mention_users"
ATTR_MENTION_ROOM: Final = "mention_room"
ATTR_THREAD_ID: Final = "thread_id"
ATTR_MEDIA: Final = "media"
ATTR_ROOM: Final = "room"
ATTR_EVENT_ID: Final = "event_id"
ATTR_REPLY_TO: Final = "reply_to"
ATTR_REACTION: Final = "reaction"
ATTR_REASON: Final = "reason"
ATTR_ACTIONS: Final = "actions"
ATTR_ROUTE: Final = "route"
ATTR_NOTIFICATION_KEY: Final = "notification_key"

FORMAT_TEXT: Final = "text"
FORMAT_HTML: Final = "html"
FORMAT_MARKDOWN: Final = "markdown"
MESSAGE_TYPES: Final = {"text", "notice", "emote"}
MEDIA_TYPES: Final = {"auto", "image", "video", "audio", "file"}

MAX_MEDIA_BYTES: Final = 128 * 1024 * 1024
HTTP_TIMEOUT_SECONDS: Final = 30
MAX_INCOMING_MEDIA_BYTES: Final = 32 * 1024 * 1024

EVENT_MESSAGE: Final = "matrix_extended_message"
EVENT_REPLY: Final = "matrix_extended_reply"
EVENT_REACTION: Final = "matrix_extended_reaction"
EVENT_MEDIA: Final = "matrix_extended_media"
EVENT_LOCATION: Final = "matrix_extended_location"
EVENT_EDIT: Final = "matrix_extended_edit"
EVENT_REDACTION: Final = "matrix_extended_redaction"
EVENT_DELIVERY: Final = "matrix_extended_delivery"
EVENT_COMMAND: Final = "matrix_extended_command"
EVENT_VOICE_ASSIST: Final = "matrix_extended_voice_assist"
