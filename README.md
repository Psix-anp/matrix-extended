<p align="center">
  <img src="custom_components/matrix_extended/brand/icon.png" width="96" alt="Matrix Extended">
</p>

<h1 align="center">Matrix Extended for Home Assistant</h1>

<p align="center">Secure two-way Matrix messaging for Home Assistant: E2EE, media, notify entities, incoming events, reactions, voice, location and resilient delivery.</p>

<p align="center"><a href="README.md"><strong>English</strong></a> · <a href="README.ru.md">Русский</a></p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.5-blue">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5">
  <img alt="Matrix" src="https://img.shields.io/badge/Matrix-E2EE-0DBD8B">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

## Highlights

- End-to-end encrypted text and media with persistent crypto state.
- Main `notify` entity plus room-specific `notify.*` entities.
- Graphical Home Assistant action editor for account selection, media browsing, TTS/STT entities, languages, location entities, reaction actions and common message fields.
- Home Assistant Media Browser support, including Local Media, Frigate and other Media Source providers.
- Text, notice, emote, Markdown/HTML, mentions, threads, replies, reactions, edits and redactions.
- Updateable notifications using `notification_key`.
- Incoming message, reply, reaction, media, location, edit and redaction events.
- Rich **Last incoming event** diagnostic entity with sender, room, event ID and type-specific attributes.
- Home Assistant TTS → Matrix voice, Matrix voice → Home Assistant STT, optional explicit Assist processing.
- Persistent outbox for temporary Matrix outages.
- Russian and English Home Assistant UI.

## Installation

### HACS

Add this repository to HACS as a custom **Integration** repository, install **Matrix Extended**, restart Home Assistant, then open **Settings → Devices & services → Add integration → Matrix Extended**.

### Manual

Copy `custom_components/matrix_extended` into `/config/custom_components/matrix_extended`, restart Home Assistant and add the integration from **Settings → Devices & services**.

The Matrix password is used only for the first login. Matrix Extended stores the resulting access token and E2EE crypto state for subsequent sessions.

## Graphical setup

Initial setup asks for homeserver, Matrix user ID, password, default room and security defaults. After setup open **Settings → Devices & services → Matrix Extended → Configure**. The options are split into clear graphical sections:

- **General** — default room, TLS validation and E2EE requirement.
- **Incoming & security** — enable incoming events and manage allowed Matrix users/rooms.
- **Incoming media** — download toggle, retention and storage limit.
- **Notification routes** — add, edit and delete named room groups without JSON.

See [Settings guide](docs/SETTINGS.md) for details and security behavior.

## Actions and automations

Home Assistant's graphical action editor is the preferred way to build automations. YAML remains fully supported and can always be selected with **Edit in YAML**.

Core actions include `matrix_extended.send`, `send_media`, `send_voice`, `transcribe_voice`, `send_location`, `reply`, `react`, `edit`, `redact` and `purge_media`.

See [Actions and events](docs/ACTIONS.md) for every action, incoming event, response field and diagnostic entity. See [YAML examples](docs/EXAMPLES.md) for ready-to-copy automations.

### Media Browser

`matrix_extended.send_media` opens the native Home Assistant Media Browser and does not restrict provider-specific media classes. Frigate clips/snapshots, Local Media and other Media Source providers can therefore be selected graphically when the provider exposes them to Home Assistant.

For cameras, URLs, local paths, multiple attachments, thumbnails or explicit media metadata, use the structured **Advanced media** field in `matrix_extended.send` or YAML.

## Incoming security

Incoming processing is fail-closed. When incoming events are enabled, **both** the sender and room must be present in the configured allowlists. Own transaction echoes are ignored. Do not treat Matrix chat text as an unrestricted remote command channel.

Reaction actions are explicitly attached to an outgoing Matrix event and can use expiry, usage limits and allowed-user restrictions. Matrix text, YAML and Jinja received from chat are not executed as arbitrary Home Assistant actions.

## Diagnostics

The integration device exposes connection status, default-room encryption, last successful send, last error and the last incoming event. The last incoming event state is the event kind (`message`, `reaction`, `media`, etc.) with useful Matrix metadata in its attributes.

## Verification

Release packaging is gated by unit/regression tests plus a disposable real stack using Home Assistant 2026.9.2, Synapse 1.160.0 and Element Web 1.12.26. The CI verifies E2EE installation, encrypted send/decrypt, notify entities, media action execution, incoming events, outage/reconnect, restart and package integrity.

Contributor details are in [Testing](docs/TESTING.md). Release history is in [CHANGELOG.md](CHANGELOG.md).

## License

MIT. See [LICENSE](LICENSE).
