# Matrix Extended v0.1 Design

## Goal
Build a compact HACS-compatible Home Assistant custom integration that turns Matrix into a practical notification transport for text and rich media without replacing or patching Home Assistant Core's legacy `matrix` integration.

## Scope
`matrix_extended` is outbound-first in v0.1. It provides a Config Flow, one modern `notify` entity per configured Matrix account, and a universal `matrix_extended.send` action. The action supports text/HTML, thread relations, multiple media attachments, Matrix captions, and four source classes: Home Assistant `camera.*`/`image.*` entities, local allowed paths, HTTP(S) URLs, and `media-source://` identifiers.

Supported Matrix message types are `m.image`, `m.video`, `m.audio`, and `m.file`. Images get width/height metadata automatically. Video/audio duration and video dimensions may be supplied explicitly; v0.1 does not depend on ffmpeg. Video/file thumbnails are optional explicit image sources.

## Authentication
The Config Flow accepts homeserver URL, Matrix user ID, password, default room, and TLS verification. It logs in once using `matrix-nio`, stores the resulting access token and device ID in the Home Assistant config entry, and does not retain the password. Runtime sessions restore the saved login and verify it with `whoami`.

## Components
- `config_flow.py`: credentials and default-room validation.
- `client.py`: Matrix login/session, room alias resolution, upload, and room send.
- `media.py`: resolve HA entities, local paths, URLs, and media sources into normalized media bytes/metadata.
- `content.py`: pure Matrix event-content construction for text, captions, metadata, thumbnails, and threads.
- `notify.py`: modern Home Assistant `NotifyEntity` using the account's default room.
- `__init__.py`: config-entry lifecycle and `matrix_extended.send` action registration.

## Data Flow
An action call selects a configured Matrix account, resolves target room(s), sends optional text, resolves each media item, uploads an optional thumbnail, uploads the media, builds a standards-compliant `m.room.message` content object, and sends it to each target room in order.

## Safety and Limits
Local files must pass Home Assistant's `is_allowed_path`. All resolved attachments are capped at 128 MiB; remote downloads are stopped as soon as that limit is exceeded and use Home Assistant's shared HTTP session. Exactly one source (`path`, `url`, `entity_id`, or `media_source`) is accepted per media item. Encrypted Matrix rooms are explicitly out of scope for v0.1.

## Errors
Invalid credentials and room aliases are surfaced in Config Flow. Runtime send/upload failures raise `HomeAssistantError` with a concise Matrix response. Unsupported entity domains, oversized attachments, and malformed media source objects fail the action rather than silently dropping content. Relative Media Source URLs are resolved against Home Assistant's internal URL when no direct filesystem path is supplied.

## Testing
Pure content/source validation helpers are covered with pytest. The package is syntax-compiled. Full Home Assistant runtime tests require the Home Assistant test harness and a Matrix homeserver and are documented as integration tests for the next repository/CI pass.
