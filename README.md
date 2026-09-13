<p align="center">
  <img src="custom_components/matrix_extended/brand/icon.png" width="96" alt="Matrix Extended">
</p>

<h1 align="center">Matrix Extended for Home Assistant</h1>

<p align="center">
  A focused Matrix integration for Home Assistant with E2EE, rich media, two-way events, resilient delivery, voice and location.
</p>

<p align="center">
  <a href="README.md"><strong>English</strong></a> · <a href="README.ru.md">Русский</a>
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.0-blue">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5">
  <img alt="Matrix" src="https://img.shields.io/badge/Matrix-E2EE-0DBD8B">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

> **0.5.0** is validated against a real **Home Assistant 2026.9.2 + Synapse 1.160.0 + Element Web 1.12.26** stack before release packaging.

## Why Matrix Extended?

Matrix Extended turns Matrix into a secure Home Assistant notification and interaction channel without turning chat text into an unrestricted remote shell.

- End-to-end encrypted text and media.
- Camera, image, local path, URL and `media-source://` attachments.
- Plain text, `notice`, `emote`, HTML and safe Markdown.
- Native Matrix mentions, replies, reactions, edits, redactions and threads.
- Per-room notify entities, room discovery, default-room selector and named routes.
- Updateable notifications via `notification_key` instead of notification spam.
- Persistent delivery outbox that survives temporary homeserver outages.
- Explicit reaction actions with expiry, usage limits and user allowlists.
- Incoming text, replies, reactions, media, edits, redactions and locations as Home Assistant events.
- Native Matrix location from coordinates or a Home Assistant location entity.
- Native Matrix voice, Home Assistant TTS → voice, voice → STT and explicit voice → Assist.
- Incoming-media retention, storage limits and manual purge.
- English and Russian Home Assistant UI translations.

## Screenshots

Real screenshots are captured by the same disposable Element Web instance used by the release E2E tests.

<p align="center">
  <img src="docs/screenshots/element-rich-e2e.png" alt="Encrypted Matrix Extended location and voice in Element" width="820">
</p>

## Installation

### HACS

Once the repository is public, add it to HACS as a custom **Integration** repository and install **Matrix Extended**.

### Manual

Copy:

```text
custom_components/matrix_extended
```

into:

```text
/config/custom_components/matrix_extended
```

Restart Home Assistant and add **Matrix Extended** from **Settings → Devices & services**.

The password is used only for the initial Matrix login. The resulting access token and persistent E2EE crypto store are used afterwards.

## Initial configuration

Recommended setup:

1. Use a dedicated Matrix bot account.
2. Invite it to an encrypted room.
3. Keep **Require E2EE** enabled.
4. Enable incoming events only when needed.
5. Configure both **Allowed users** and **Allowed rooms**. Incoming processing is fail-closed against both lists.
6. Enable incoming-media download only if your automations need local files.
7. Configure retention age and storage limit for downloaded media.

Persistent crypto state is stored under:

```text
/config/.storage/matrix_extended/<config_entry_id>/
```

Downloaded incoming files are stored under:

```text
/config/matrix_extended/incoming/<config_entry_id>/
```

## Quick examples

### Send a message

```yaml
action: matrix_extended.send
data:
  target:
    - "#security:example.org"
  message: "Motion detected at the gate"
```

### Markdown + mention

```yaml
action: matrix_extended.send
data:
  route: security
  format: markdown
  message: "**Alarm:** garage door is open"
  mention_users:
    - "@alex:example.org"
```

### Camera snapshot with safe reaction action

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Someone is at the gate"
  media:
    - entity_id: camera.gate
      caption: "Latest frame"
  actions:
    - reaction: "💡"
      service: light.turn_on
      target:
        entity_id: light.gate
      expires_in: 300
      max_uses: 1
      allowed_users:
        - "@alex:example.org"
```

A reaction can invoke only the exact Home Assistant service pre-registered on that outgoing Matrix event. Matrix text, YAML and Jinja are never interpreted as arbitrary service calls.

### Update one Matrix event instead of sending many

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "download.movie.123"
  message: "Download — 64%"
```

Later calls using the same key edit the original Matrix event with `m.replace`.

### Send location

From explicit coordinates:

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  latitude: 52.3676
  longitude: 4.9041
  description: "Current position"
```

Or from an entity exposing `latitude` and `longitude`:

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  entity_id: person.alex
```

### Send a native voice attachment

```yaml
action: matrix_extended.send
data:
  target:
    - "#family:example.org"
  media:
    - path: /config/media/voice.ogg
      type: audio
      voice: true
```

### Home Assistant TTS → Matrix voice

```yaml
action: matrix_extended.send_voice
data:
  target:
    - "#security:example.org"
  text: "Warning. The garage door is still open."
  language: en-US
```

`tts_engine` and provider-specific `tts_options` are optional.

### Matrix voice → Home Assistant STT

Use `local_path` from an incoming `matrix_extended_media` event:

```yaml
action: matrix_extended.transcribe_voice
response_variable: voice_result
data:
  path: "{{ trigger.event.data.local_path }}"
  stt_entity: stt.whisper
  language: en
```

If the STT provider cannot accept the original OGG/Opus stream, Matrix Extended uses Home Assistant FFmpeg to normalize it to a supported WAV/PCM format.

### Voice transcript → Assist

Assist execution is deliberately **off by default**. Enable it explicitly:

```yaml
action: matrix_extended.transcribe_voice
response_variable: voice_result
data:
  path: "{{ trigger.event.data.local_path }}"
  stt_entity: stt.whisper
  assist: true
```

Use Matrix incoming user/room allowlists for any automation that can reach Assist.

## Services

| Service | Purpose |
| --- | --- |
| `matrix_extended.send` | Text, Markdown/HTML, mentions, media, threads, routes and reaction actions |
| `matrix_extended.send_voice` | Home Assistant TTS → native Matrix voice |
| `matrix_extended.transcribe_voice` | Downloaded Matrix voice → Home Assistant STT; optional explicit Assist |
| `matrix_extended.send_location` | Matrix `m.location` from coordinates or HA entity |
| `matrix_extended.reply` | Rich reply to an event |
| `matrix_extended.react` | Emoji reaction |
| `matrix_extended.edit` | `m.replace` edit |
| `matrix_extended.redact` | Redact an event |
| `matrix_extended.purge_media` | Purge downloaded incoming media and return removed file/byte counts |

Service fields and selectors are documented directly in the Home Assistant action editor through `services.yaml`.

## Incoming events

| Event | Meaning |
| --- | --- |
| `matrix_extended_message` | Incoming text-like message |
| `matrix_extended_reply` | Incoming reply |
| `matrix_extended_reaction` | Incoming reaction and reaction-action result |
| `matrix_extended_media` | Incoming image/video/audio/file; voice messages are marked |
| `matrix_extended_location` | Incoming Matrix location |
| `matrix_extended_edit` | Incoming edit |
| `matrix_extended_redaction` | Incoming redaction |
| `matrix_extended_delivery` | Outgoing delivery lifecycle: `sent`, `queued`, `failed`, `dropped` |

Common incoming metadata includes account, room, sender, event ID, timestamp, encryption state and relation data. Rich payloads add room name/alias, sender display name, mentions and media metadata when available.

## Delivery responses and offline queue

`matrix_extended.send` supports response data containing a stable `delivery_id`, delivery `status` and Matrix event records. When Synapse is unavailable, supported sends can be persisted to the outbox and delivered after reconnect instead of blocking Home Assistant.

Delivery lifecycle is also emitted on `matrix_extended_delivery`, making it usable from event automations independently of a service response.

## Routing and room entities

After Matrix sync the integration exposes:

- one general `notify` entity for the current default room;
- one room-specific `notify` entity per joined room;
- a **Default room** select entity;
- diagnostic connection/user/device/room/last-send/last-receive/error entities.

Named routing profiles keep automations independent from raw Matrix room IDs:

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Alarm triggered"
```

## Security model

Matrix Extended intentionally keeps automation power explicit:

- `Require E2EE` blocks outgoing sends to plaintext rooms when enabled.
- Incoming processing is constrained by both user and room allowlists.
- Matrix message text never becomes executable YAML, Jinja or an arbitrary HA service.
- Reaction actions exist only when Home Assistant attached them to a specific outgoing event.
- Reaction actions can expire, be limited to specific users and have a maximum use count.
- Voice transcription can read only files from that Matrix account's incoming-media directory.
- Voice → Assist is explicit opt-in.
- Media purge/retention operates only inside integration-owned incoming directories.

### Upstream Matrix limitations

Matrix Extended intentionally stays on `matrix-nio==0.26.0` for this release. That version does not provide cross-signing support. It also sends `m.reaction` unencrypted, so reaction emoji and the target relation are visible to the homeserver even when the room is E2EE. Do not use reactions for secrets, PINs or passwords.

## Testing and release gate

Every release candidate must pass:

1. source validation, compile checks and regression tests;
2. a disposable real stack with Home Assistant 2026.9.2, Synapse 1.160.0 and Element Web 1.12.26;
3. real Element E2EE decryption and rich location/voice rendering;
4. Synapse outage → persistent queue → automatic recovery;
5. Home Assistant restart and persisted reaction-action behavior;
6. clean runtime logs/background tasks;
7. install ZIP creation and byte-for-byte verification against the component tree, with SHA-256 checksum.

See [`docs/TESTING.md`](docs/TESTING.md) for the test harness.

## Upgrade from 0.4.x

Existing config entries, access tokens, crypto stores, routing profiles and notification mappings are retained. New 0.5 options use safe defaults. Existing `matrix_extended.send` YAML keeps its original plain-text behavior unless the new fields are used.

## License

MIT — see [`LICENSE`](LICENSE).
