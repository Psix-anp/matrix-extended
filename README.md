<p align="center">
  <img src="custom_components/matrix_extended/brand/icon.png" width="96" alt="Matrix Extended">
</p>

<h1 align="center">Matrix Extended for Home Assistant</h1>

<p align="center">Secure two-way Matrix messaging for Home Assistant: E2EE, media, notify entities, incoming events, reactions, voice, location and resilient delivery.</p>

<p align="center"><a href="README.md"><strong>English</strong></a> · <a href="README.ru.md">Русский</a></p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.6-blue">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5">
  <img alt="Matrix" src="https://img.shields.io/badge/Matrix-E2EE-0DBD8B">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
  <img alt="AI-assisted" src="https://img.shields.io/badge/AI--assisted-OpenAI%20%2F%20ChatGPT-412991">
</p>

<p align="center"><sub>AI-assisted development, testing and documentation with OpenAI / ChatGPT. Project decisions and maintenance remain with <a href="https://github.com/Psix-anp">Psix-anp</a>.</sub></p>

## Highlights

- End-to-end encrypted text and media with persistent crypto state.
- Main `notify` entity plus room-specific `notify.*` entities.
- Graphical Home Assistant action editor for account selection, media browsing, TTS/STT entities, languages, location entities, reaction actions and common message fields.
- Home Assistant Media Browser support, including Local Media, Frigate and other Media Source providers.
- Text, notice, emote, Markdown/HTML, mentions, threads, replies, reactions, edits and redactions.
- Updateable notifications using `notification_key`.
- Incoming message, reply, reaction, media, location, edit and redaction events.
- Home Assistant TTS → Matrix voice, Matrix voice → Home Assistant STT, plus optional automatic Voice Assist.
- Safe predefined Matrix commands with Home Assistant service and camera-snapshot handlers.
- Persistent outbox for temporary Matrix outages.
- Russian and English Home Assistant UI and documentation.

## Installation

### HACS default catalog

Once Matrix Extended is accepted into the HACS default catalog, open **HACS → Integrations**, search for **Matrix Extended**, install it and restart Home Assistant.

### HACS custom repository

Until the default-catalog review is complete, use the public repository directly:

1. Open **HACS → Integrations**.
2. Open the HACS menu and choose **Custom repositories**.
3. Add `https://github.com/Psix-anp/matrix-extended` as category **Integration**.
4. Search for **Matrix Extended** and install it.
5. Restart Home Assistant.

HACS installs the integration under `/config/custom_components/matrix_extended`.

### Manual installation

Download the install ZIP from the latest GitHub Release, extract `custom_components/matrix_extended` into `/config/custom_components/matrix_extended`, then restart Home Assistant. Installing from a verified release asset is preferred over copying arbitrary development snapshots.

## First connection

After installation and restart:

1. Open **Settings → Devices & services → Add integration**.
2. Search for **Matrix Extended**.
3. Fill in the connection form:
   - **Homeserver (`homeserver`)** — your Matrix Client API base URL, for example `https://matrix.example.org`.
   - **Matrix user ID (`user_id`)** — full Matrix ID, for example `@homeassistant:example.org`.
   - **Password** — used only for the initial Matrix login. Matrix Extended exchanges it for an access token; the password itself is not stored by the integration.
   - **Default room (`default_room`)** — room ID such as `!abc:example.org` or alias such as `#home:example.org`. Aliases are resolved during setup.
   - **Verify TLS (`verify_ssl`)** — keep enabled for normal HTTPS homeservers. Disable only for a deliberately trusted local/test server.
   - **Require E2EE (`require_e2ee`)** — enabled by default. When enabled, outbound delivery to plaintext rooms is refused.
   - **Enable incoming events (`incoming_enabled`)** — enabled by default.
   - **Allowed users (`allowed_users`)** — senders allowed to reach Home Assistant. If left empty during initial setup, your logged-in Matrix user is used.
   - **Allowed rooms (`allowed_rooms`)** — rooms allowed to reach Home Assistant. If left empty during initial setup, the default room is used.
   - **Download incoming media (`download_incoming_media`)** — enables local download/decryption so incoming attachments and voice messages can be used by automations.
4. Submit the form. Matrix Extended logs in, validates/resolves the default room, stores the resulting access token/device ID and initializes persistent E2EE state.
5. Open the created Matrix Extended device and verify that the connection diagnostic becomes connected.

For inbound automation, both the sender and room must pass the allowlists. This is deliberately fail-closed.

## Configure after setup

Open **Settings → Devices & services → Matrix Extended → Configure**. The graphical options menu contains five sections:

- **General** — default room, TLS verification and E2EE policy.
- **Incoming & security** — incoming-event toggle and sender/room allowlists.
- **Incoming media** — download toggle, retention period and storage quota.
- **Voice Assist** — automatic Matrix voice → STT → Home Assistant Assist processing, reply mode (`text`, `voice`, or `both`), STT/TTS entities, language, conversation agent and additional trusted users/rooms.
- **Notification routes** — add, edit and delete reusable named room groups without raw JSON.

The integration also exposes a **Default room** select entity for joined rooms.

See the full [Settings and connection guide](docs/SETTINGS.md).

## Actions and automations

Home Assistant's graphical action editor is the preferred way to build automations. YAML remains fully supported and can always be selected with **Edit in YAML**.

Current actions:

- `matrix_extended.send`
- `matrix_extended.send_media`
- `matrix_extended.send_voice`
- `matrix_extended.transcribe_voice`
- `matrix_extended.send_location`
- `matrix_extended.reply`
- `matrix_extended.react`
- `matrix_extended.edit`
- `matrix_extended.redact`
- `matrix_extended.purge_media`
- `matrix_extended.register_command`
- `matrix_extended.unregister_command`

See [Actions and events](docs/ACTIONS.md) for fields, defaults, constraints and response data. See [Practical examples](docs/EXAMPLES.md) for ready-to-copy automations, including both safe-command handler modes and Matrix voice → STT/Assist.

## Media Browser

`matrix_extended.send_media` opens the native Home Assistant Media Browser and accepts provider-specific media classes. Frigate clips/snapshots, Local Media and other Media Source providers can therefore be selected graphically when the provider exposes them to Home Assistant.

For cameras, URLs, local paths, multiple attachments, thumbnails or explicit media metadata, use the structured `media` field in `matrix_extended.send`.

## Incoming security

Incoming processing is fail-closed: when enabled, **both** sender and room must match the configured allowlists. Own transaction echoes are ignored.

Reaction actions and safe Matrix commands are explicit stored actions. Incoming Matrix text is never interpreted as arbitrary Home Assistant YAML/Jinja or as an unrestricted service call.

Automatic Voice Assist is opt-in and has its own optional trusted-user/room restrictions. Use it only in rooms and with senders you trust to issue Assist requests.

## Diagnostics and storage

The integration device exposes connection state, Matrix user/device IDs, default room and encryption state, last successful send, last incoming event, last error, safe-command state and delivery diagnostics.

Incoming downloaded media is scoped per config entry under:

```text
/config/matrix_extended/incoming/<config_entry_id>/
```

E2EE crypto state and integration registries are stored under Home Assistant storage. Do not manually edit them while Home Assistant is running.

## Verification

Release packaging is gated by regression tests plus a disposable real stack using Home Assistant 2026.9.2, Synapse 1.160.0 and Element Web 1.12.26. The CI verifies E2EE dependencies, Home Assistant service metadata parsing, encrypted send/decrypt, notify entities, Media Browser send, safe commands, automatic Voice Assist, outage/reconnect, Home Assistant restart, background-task cleanup and package integrity.

Public-distribution validation also runs HACS validation and Home Assistant Hassfest.

Contributor details are in [Testing](docs/TESTING.md). Release history is in [CHANGELOG.md](CHANGELOG.md). Authorship and maintenance are documented in [AUTHORS.md](AUTHORS.md).

## License

MIT. See [LICENSE](LICENSE).
