# Matrix Extended actions and events

Home Assistant's graphical action editor is the preferred interface. The same actions remain available in YAML.

## Outbound actions

### `matrix_extended.send`

General-purpose Matrix send action.

Use it for text, Markdown/HTML, mentions, threads, updateable notifications, multiple/advanced media items, and safe reaction actions.

Important fields:

- **Account** — Matrix Extended config entry; can be omitted in YAML when only one account exists.
- **Rooms** — one or more Matrix room IDs/aliases.
- **Route** — named route from integration settings; mutually exclusive with Rooms.
- **Notification key** — stable key; later sends with the same key edit the original Matrix event.
- **Message type** — `text`, `notice`, or `emote`.
- **Format** — `text`, `html`, or `markdown`.
- **Mention users / Mention room** — native Matrix mentions.
- **Thread ID** — event ID of the thread root.
- **Advanced media** — structured attachments from Home Assistant entities, local paths, URLs, or Media Source IDs.
- **Reaction actions** — explicit Home Assistant actions attached to reactions on this outgoing event.

`matrix_extended.send` supports response data and emits `matrix_extended_delivery` lifecycle events.

### `matrix_extended.send_media`

Opens the native Home Assistant Media Browser and sends one selected Media Source item to Matrix. The selector accepts all Media Source types so provider-specific items such as Frigate clips/snapshots are not filtered out.

Use `matrix_extended.send` → **Advanced media** for cameras, URLs, local paths, multiple attachments, thumbnails, native-voice metadata, or explicit media dimensions/duration.

### `matrix_extended.send_voice`

Synthesizes text with Home Assistant TTS and sends the result as a native Matrix voice message.

The graphical editor can select a `tts.*` entity and language. Provider-specific `tts_options` remains an advanced object because each TTS integration defines its own keys.

### `matrix_extended.transcribe_voice`

Transcribes a downloaded incoming Matrix voice file through Home Assistant STT. The path is restricted to the selected Matrix account's incoming-media directory.

If the selected STT provider requires WAV/PCM, Matrix Extended can normalize supported input through Home Assistant FFmpeg.

`assist: true` is explicit opt-in. Voice messages do not reach Home Assistant Assist by default.

### `matrix_extended.send_location`

Sends Matrix location data either from explicit latitude/longitude or from a Home Assistant entity exposing `latitude` and `longitude` attributes.

### `matrix_extended.reply`

Replies to an existing Matrix event ID. Supports message type, format, mentions, and threads.

### `matrix_extended.react`

Adds a Matrix reaction to an existing event.

With matrix-nio 0.26.0, `m.reaction` itself is not encrypted. Do not use reaction content for secrets.

### `matrix_extended.edit`

Edits a text-like Matrix event using `m.replace`.

### `matrix_extended.redact`

Redacts an existing Matrix event.

### `matrix_extended.purge_media`

Deletes downloaded incoming media owned by the selected Matrix Extended account and can return removed file/byte counts.

## Reaction actions

Reaction actions are registered only when Home Assistant sends a message containing an explicit reaction-action definition. A definition can include:

- reaction key;
- exact Home Assistant action/service;
- target and data;
- expiry in seconds;
- maximum use count;
- allowed Matrix users.

Incoming Matrix text, YAML, or Jinja is never interpreted as an arbitrary Home Assistant action.

## Notify entities

Each account exposes a default-room `notify` entity and room-specific `notify` entities discovered from joined Matrix rooms. Use Home Assistant's standard `notify.send_message` entity action when building graphical automations around these entities.

The Matrix Extended-specific actions remain available when you need routes, response data, advanced media, reactions, threads, voice, or other Matrix-specific options.

## Incoming events

When incoming processing is enabled and both sender/room allowlists match, Matrix Extended emits:

| Event | Purpose |
| --- | --- |
| `matrix_extended_message` | Incoming text-like message |
| `matrix_extended_reply` | Incoming reply |
| `matrix_extended_reaction` | Incoming reaction and reaction-action result metadata |
| `matrix_extended_media` | Incoming image/video/audio/file; voice is marked separately |
| `matrix_extended_location` | Incoming Matrix location |
| `matrix_extended_edit` | Incoming edit |
| `matrix_extended_redaction` | Incoming redaction |
| `matrix_extended_delivery` | Outbound delivery lifecycle: `sent`, `queued`, `failed`, `dropped` |

Common incoming metadata includes account/config-entry context, room, sender, event ID, timestamp and encryption state. Type-specific events add relation, media, voice, location or edit/redaction fields.

## Last incoming event diagnostic

The **Last incoming event** sensor exposes the event kind as its state and event metadata as attributes, including sender, room and event ID when available. The state is localized in Home Assistant.

## Offline delivery

When the Matrix homeserver becomes unavailable, supported outgoing sends can be persisted in the integration outbox. The integration reports the disconnect, queues the send, and retries after reconnection instead of blocking Home Assistant's event loop.

For copy/paste automation examples, see [EXAMPLES.md](EXAMPLES.md). For integration configuration, see [SETTINGS.md](SETTINGS.md).
