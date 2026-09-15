# Matrix Extended actions and events

**English** · [Русский](ACTIONS.ru.md)

Home Assistant's graphical action editor is the preferred interface. YAML remains fully supported and is useful for templates, `response_variable`, and advanced objects.

## Common routing rules

Several actions share `account`, `target`, `route`, and `thread_id`:

- `account` — Matrix Extended config entry. It may be omitted in YAML only when exactly one account is loaded.
- `target` — one or more Matrix room IDs/aliases.
- `route` — a named routing profile from Matrix Extended settings. Do not combine it with `target`.
- if neither `target` nor `route` is provided, the account's default room is used.
- `thread_id` — event ID of the Matrix thread root. A reply target uses a separate `event_id`.

`send`, `send_voice`, and `send_location` can return delivery data:

```yaml
delivery_id: "..."
status: sent
events:
  - room_id: "!room:example.org"
    event_id: "$event"
    kind: text
```

Media delivery records can also include `media_index`. Lifecycle states are `sent`, `queued`, `failed`, and `dropped`.

## `matrix_extended.send`

General-purpose text and/or advanced media send. Supports E2EE, Markdown/HTML, native mentions, threads, updateable notifications, and bounded reaction actions.

### Fields

| Field | Required | Default | Meaning |
| --- | --- | --- | --- |
| `account` | no | only account | Matrix Extended config entry |
| `target` | no | default room | room list; mutually exclusive with `route` |
| `route` | no | — | named route; mutually exclusive with `target` |
| `notification_key` | no | — | stable updateable-notification key; later sends edit the original event |
| `message` | no* | `""` | text body; may be empty only when `media` is present |
| `msgtype` | no | `text` | `text`, `notice`, or `emote` |
| `format` | no | `text` | `text`, `markdown`, or `html` |
| `mention_users` | no | `[]` | Matrix user IDs for native `m.mentions` |
| `mention_room` | no | `false` | native room-wide mention |
| `thread_id` | no | — | thread-root event ID |
| `media` | no* | `[]` | one or more advanced attachments |
| `actions` | no | `[]` | explicit HA actions bound to reactions |

At least `message` or `media` is required. `notification_key` and reaction `actions` require a text message.

### `media` object

Each media item must contain exactly one source:

- `entity_id` — Home Assistant entity, commonly `camera.*`;
- `path` — local path allowed by Home Assistant;
- `url` — HTTP/HTTPS URL;
- `media_source` — Home Assistant Media Source ID.

Optional metadata:

- `type` — `auto`, `image`, `video`, `audio`, `file`;
- `filename` — Matrix filename;
- `caption` — caption/body;
- `formatted_caption` — HTML caption; requires `caption`;
- `width`, `height` — dimensions;
- `duration_ms` — duration in milliseconds;
- `voice` — mark audio as native Matrix voice;
- `thumbnail` — YAML-only nested media object used as a thumbnail; nested thumbnails are rejected.

### Reaction `actions`

Each object contains:

- `reaction` — reaction key such as `✅`;
- `service` — fixed HA action in `domain.service` format;
- `target`, `data` — stored HA action arguments;
- `expires_in` — 1…604800 seconds, default 3600;
- `max_uses` — 1…100, default 1;
- `allowed_users` — optional Matrix-user restriction.

Incoming Matrix content cannot replace the stored service, target, or data.

Examples: [EXAMPLES.md — send](EXAMPLES.md#1-matrix_extendedsend--general-send).

## `matrix_extended.send_media`

Convenience action for one Home Assistant Media Browser item, including provider-specific sources such as Local Media and Frigate.

| Field | Required | Default | Meaning |
| --- | --- | --- | --- |
| `account` | no | only account | Matrix Extended config entry |
| `target` | no | default room | destination rooms |
| `route` | no | — | route instead of `target` |
| `media_picker` | yes | — | object produced by the HA Media Browser selector |
| `caption` | no | — | Matrix caption |
| `voice` | no | `false` | mark selected audio as native Matrix voice |
| `thread_id` | no | — | thread root |

For cameras, URLs, multiple attachments, thumbnails, or explicit metadata, use `send` with `media` instead.

Starting with v0.5.6, protected internal HA Media Source URLs are processed through Home Assistant's temporary `authSig`; Frigate timestamp VOD selections are converted to the HA MP4 recording proxy before upload.

Examples: [EXAMPLES.md — send_media](EXAMPLES.md#2-matrix_extendedsend_media--media-browser).

## `matrix_extended.send_voice`

Converts text through Home Assistant TTS and sends the generated audio as native Matrix voice.

| Field | Required | Default | Meaning |
| --- | --- | --- | --- |
| `account` | no | only account | Matrix Extended config entry |
| `target` / `route` | no | default room | destination |
| `text` | yes | — | non-empty text to synthesize |
| `tts_engine` | no | default TTS | `tts.*` entity or compatible provider ID |
| `language` | no | provider/default | language/locale; compatible locale variants are matched |
| `tts_options` | no | `{}` | provider-specific options such as voice selection |
| `thread_id` | no | — | thread root |

Returns `delivery_id`, `status`, and `events`.

Examples: [EXAMPLES.md — send_voice](EXAMPLES.md#3-matrix_extendedsend_voice--tts--matrix-voice).

## `matrix_extended.transcribe_voice`

Transcribes an incoming Matrix voice file through Home Assistant STT. If the provider does not accept the original OGG/Opus metadata, Matrix Extended can normalize the file to WAV/PCM using Home Assistant FFmpeg.

Each Matrix account owns a separate incoming directory:

`/config/matrix_extended/incoming/<config_entry_id>/`

The actual root is built through `hass.config.path(...)`, so `/config` may differ on unusual installations. Normal automations should pass `trigger.event.data.local_path` from `matrix_extended_media` directly.

For safety, only regular files inside that account's incoming directory are accepted; traversal, symlinks, and files belonging to another account are rejected.

| Field | Required | Default | Meaning |
| --- | --- | --- | --- |
| `account` | no | only account | account that owns the incoming file |
| `path` | yes | — | full `local_path` or path relative to the account incoming directory |
| `stt_entity` | no | default STT | `stt.*` entity |
| `language` | no | HA language | requested recognition language |
| `audio_format` | no | `ogg` | `ogg` or `wav` |
| `codec` | no | `opus` | `opus` or `pcm` |
| `bit_rate` | no | `16` | `8`, `16`, `24`, `32` |
| `sample_rate` | no | `48000` | supported selector values from 8000 through 48000 Hz |
| `channels` | no | `1` | `1` or `2` |
| `assist` | no | `false` | explicitly pass transcript to HA Conversation/Assist |
| `conversation_agent` | no | default agent | optional `conversation.*` agent |
| `conversation_id` | no | new | optional existing conversation ID |

Response keys: `text`, `stt_entity`, `language`, `normalized`, `assist_executed`, plus `assist` when Assist ran.

Examples: [EXAMPLES.md — transcribe_voice](EXAMPLES.md#4-matrix_extendedtranscribe_voice--matrix-voice--sttassist).

## `matrix_extended.send_location`

Sends standard Matrix `m.location` in one of two mutually exclusive modes: entity or explicit coordinates.

Fields: `account`, `target`/`route`, `entity_id`, `latitude`, `longitude`, `description`, `thread_id`.

Use either an entity exposing `latitude` and `longitude`, or both explicit coordinates. Do not mix the two modes. Returns delivery data.

Examples: [EXAMPLES.md — send_location](EXAMPLES.md#5-matrix_extendedsend_location--location).

## `matrix_extended.reply`

Replies to an existing Matrix event.

Fields: optional `account`, optional single `room` (default room otherwise), required `event_id` and `message`, optional `msgtype`, `format`, `mention_users`, `mention_room`, and `thread_id`.

Typical automations take `room` and `event_id` directly from an incoming Matrix Extended event.

Examples: [EXAMPLES.md — reply](EXAMPLES.md#6-matrix_extendedreply--reply-to-an-incoming-event).

## `matrix_extended.react`

Adds an `m.reaction` annotation to an existing event. Fields: optional `account`, optional `room`, required `event_id`, and required `reaction`.

With matrix-nio 0.26.0, `m.reaction` itself is not encrypted. Do not place secrets in the reaction key.

Examples: [EXAMPLES.md — react](EXAMPLES.md#7-matrix_extendedreact--reaction).

## `matrix_extended.edit`

Edits a text-like Matrix event via `m.replace`. Fields: optional `account`/`room`, required `event_id`/`message`, optional `msgtype` and `format`.

For frequently updated status messages, `send` + `notification_key` is usually simpler. Use `edit` when you already have the target event ID.

Examples: [EXAMPLES.md — edit](EXAMPLES.md#8-matrix_extendededit--edit-a-message).

## `matrix_extended.redact`

Performs Matrix redaction on an existing event. Fields: optional `account`/`room`, required `event_id`, optional `reason`. This is server-side Matrix redaction, not a local Home Assistant delete.

Examples: [EXAMPLES.md — redact](EXAMPLES.md#9-matrix_extendedredact--redaction).

## `matrix_extended.purge_media`

Deletes downloaded incoming media for the selected account. The only field is optional `account`; it can be omitted only when one account is loaded.

Response data:

```yaml
removed_files: 12
removed_bytes: 3456789
```

Examples: [EXAMPLES.md — purge_media](EXAMPLES.md#10-matrix_extendedpurge_media--incoming-media-cleanup).

## `matrix_extended.register_command`

Registers or replaces one deterministic safe Matrix command. Incoming Matrix text can only select the stored command; it cannot replace the HA service, target/data, or camera entity.

Common fields:

| Field | Required | Default | Meaning |
| --- | --- | --- | --- |
| `account` | no | only account | Matrix Extended config entry |
| `id` | yes | — | stable command ID; registering the same ID replaces it |
| `trigger` | yes | — | normalized phrase without leading `!` |
| `aliases` | no | `[]` | alternate phrases |
| `description` | no | `""` | description |
| `allowed_users` | no | `[]` | additional restriction on top of account allowlist |
| `allowed_rooms` | no | `[]` | additional room restriction |
| `progress` | no | `true` | send progress reply while executing |
| `handler_type` | yes | — | `service` or `camera_snapshot` |

For `handler_type: service`, `service` is required and `target`/`data` are stored arguments; `entity_id` is rejected.

For `handler_type: camera_snapshot`, `entity_id` must be a `camera.*` entity and `caption` is optional (default `Camera snapshot`); `service`, `target`, and `data` are rejected.

Response: `id`, `trigger`, `handler_type`.

Examples for both modes: [EXAMPLES.md — register_command](EXAMPLES.md#11-matrix_extendedregister_command--safe-commands).

## `matrix_extended.unregister_command`

Removes a safe command by stable ID. Fields: optional `account`, required `id`.

Response: `id` and boolean `removed`. `removed: false` means the ID was already absent.

Example: [EXAMPLES.md — unregister_command](EXAMPLES.md#12-matrix_extendedunregister_command--remove-a-command).

## Notify entities

Each account exposes a default-room `notify` entity and room-specific notify entities for joined rooms. Use standard Home Assistant `notify.send_message` for ordinary text. Matrix Extended actions are for Matrix-specific routing, response data, rich media, reactions, threads, voice, and related features.

## Incoming events

When incoming handling is enabled and sender/room allowlists both pass, Matrix Extended emits:

| Event | Purpose |
| --- | --- |
| `matrix_extended_message` | incoming text-like message |
| `matrix_extended_reply` | incoming reply |
| `matrix_extended_reaction` | incoming reaction and reaction-action metadata |
| `matrix_extended_media` | image/video/audio/file; voice is flagged separately |
| `matrix_extended_location` | Matrix location |
| `matrix_extended_edit` | edit |
| `matrix_extended_redaction` | redaction |
| `matrix_extended_delivery` | `sent`, `queued`, `failed`, `dropped` lifecycle |

Common metadata includes account/config-entry context, room, sender, event ID, timestamp, and encryption state. Incoming media additionally exposes fields such as `voice`, `content_type`, `local_path`, and `download_error`.

## Offline delivery

When the homeserver is temporarily unavailable, supported `send` calls are persisted in the outbox. `matrix_extended_delivery` reports `queued`, then `sent` after recovery or `dropped` for a permanent failure.

Copy/paste automations: [EXAMPLES.md](EXAMPLES.md). Integration settings: [SETTINGS.md](SETTINGS.md).
