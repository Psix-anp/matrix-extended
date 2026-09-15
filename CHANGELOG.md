# Changelog

## 0.5.7 — 2026-09-15

Image Media Source snapshot fix and graphical URL/entity media sending.

- Fix Home Assistant `media-source://image/...` selections by fetching one native image frame through `image.async_get_image()` instead of trying to download the `/api/image_proxy_stream/...` streaming endpoint as a finite attachment.
- Extend `matrix_extended.send_media` to accept exactly one graphical source: Home Assistant Media Browser, direct HTTP/HTTPS URL, or `camera.*` / `image.*` entity.
- Add media type override and optional filename to `send_media` while retaining caption, native voice and thread support for the new source modes.
- Keep existing Media Browser automations and the Frigate MP4/VOD handling introduced in v0.5.6 compatible.
- Fix the top README integration image for HACS/embedded rendering by using an absolute raw GitHub URL.
- No migration is required.

### Verification

- TDD RED reproduced the missing behavior with 7 failed / 297 passed before implementation.
- The final feature head passed regression, clean Python 3.14 + E2EE, real Home Assistant 2026.9.2 + Synapse 1.160.0 + Element 1.12.26, real `services.yaml` parsing, graphical `send_media`, outage/recovery, Home Assistant restart, background-task cleanup, verified install ZIP, Hassfest and HACS validation.
- The final v0.5.7 release is published only after the exact release commit passes the same mandatory gates.

## 0.5.6 — 2026-09-15

Media Source authentication hardening, complete action recipes, and public/HACS readiness.

- Fix authenticated Home Assistant Media Source downloads used by `matrix_extended.send_media` by processing internal Home Assistant URLs through the native signed-media URL path instead of downloading protected endpoints anonymously.
- Convert Frigate timestamp VOD manifests to the Frigate MP4 recording proxy before Matrix upload so selected clips are sent as actual video instead of an HLS playlist.
- Expand English and Russian action documentation for all Matrix Extended actions with field descriptions, defaults, response data, and ready-to-copy Home Assistant automations.
- Add verified Matrix voice → STT and STT → Assist recipes, including safe boolean conditions for `matrix_extended_media` events.
- Rewrite installation, first-connection, settings, Voice Assist, safe-command, HACS custom-repository, and public-distribution documentation.
- Add transparent AI-assisted development disclosure for OpenAI / ChatGPT while keeping project decisions and maintenance attributed to Psix-anp.
- Add Home Assistant Hassfest validation and public-repository/HACS readiness contracts.
- Keep existing automations compatible; no migration is required.

### Verification

- Feature and documentation PRs passed regression, clean Python 3.14 + E2EE, real Home Assistant 2026.9.2 + Synapse 1.160.0 + Element 1.12.26, and verified install-ZIP gates before merge.
- Public-readiness changes passed Hassfest.
- Final v0.5.6 release is published only after the release commit passes the same mandatory gates.

## 0.5.5 — 2026-09-14

Safe Matrix commands, encrypted camera snapshots and automatic Voice Assist.

- Add fail-closed `matrix_extended.register_command` and `matrix_extended.unregister_command` actions for exact allowlisted Matrix commands with persisted definitions.
- Keep Home Assistant action, target, data and camera entity stored server-side so incoming Matrix text can select a registered command but cannot override what it executes.
- Add an encrypted `camera_snapshot` command handler that captures a configured `camera.*` entity and returns the image to Matrix.
- Add optional automatic native Matrix voice processing: decrypt/download → Home Assistant STT → Conversation/Assist → Matrix reply.
- Add separate Voice Assist user/room restrictions that can only narrow the normal incoming allowlists, plus `text`, `voice` and `both` reply modes.
- Add a dedicated graphical **Voice Assist** section to the Home Assistant Options Flow.
- Add E2EE readiness, outbox size, last delivery status and last command diagnostics with English and Russian translations.
- Verify `services.yaml` with the real Home Assistant 2026.9.2 parser, including the new command actions.
- Verify encrypted safe commands, camera snapshots and automatic Voice Assist on the full Home Assistant 2026.9.2 + Synapse 1.160.0 + Element 1.12.26 stack.
- Re-verify encrypted send/reload, notify entities, Element rendering, `send_media`, Synapse outage recovery, persistent outbox, Home Assistant restart and background-task cleanup.

### Compatibility notes

- No breaking changes are required for existing automations.
- Automatic Voice Assist remains opt-in and disabled by default.
- Safe Matrix commands execute only pre-registered definitions and remain fail-closed for unregistered or disallowed input.

## 0.5.4 — 2026-09-14

Graphical-first Home Assistant UX and public repository cleanup.

- Split the options flow into **General**, **Incoming & security**, **Incoming media**, and **Notification routes**.
- Replace raw route JSON editing with graphical add/edit/delete flows.
- Make the default room and TLS validation editable from the integration UI and ensure runtime reload uses the saved values.
- Prefer native Home Assistant selectors for config entries, TTS/STT entities, language, location entities, Media Browser, targets and structured advanced fields.
- Keep YAML compatibility for all actions and advanced provider-specific options.
- Localize diagnostic states such as encryption and incoming-event type; show `No errors` instead of an unknown state when the error buffer is clear.
- Refresh English/Russian documentation and remove internal planning/spec/mutation-testing clutter from the user-facing repository.
- Replace release-number-specific structure tests with current behavior/contract coverage and remove hard-coded release version maintenance from source validation.

## 0.5.3 — 2026-09-14

Runtime hotfixes verified on the full Home Assistant + Synapse + Element stack.

- Fix `matrix_extended.send_media` service handler registration so Home Assistant invokes the graphical media action with the correct handler signature.
- Fix Media Source browsing/delivery compatibility used by the graphical picker.
- Improve TTS locale fallback when a provider exposes a compatible language with a different locale granularity.
- Keep native Matrix voice delivery metadata consistent.
- Expand the **Last incoming event** diagnostic with event kind and event-specific metadata.
- Add real-stack regression coverage for the `send_media` action and rich incoming-event diagnostics.

## 0.5.2 — 2026-09-14

Localized actions and graphical media selection.

- Add `matrix_extended.send_media` with the native Home Assistant Media Browser.
- Add English and Russian action/field translations and translated selector options.
- Verify default and room-specific Matrix notify entities in real Home Assistant.
- Keep the existing advanced media model for cameras, URLs, local paths, multiple attachments and Matrix-specific metadata.

## 0.5.1 — 2026-09-14

Home Assistant 2026.9 runtime/install hotfix.

- Install Matrix E2EE support through `matrix-nio[e2e]==0.26.0` from the integration manifest, not only from the test environment.
- Fix numeric action-selector metadata so `services.yaml` is accepted by Home Assistant's real service metadata schema.
- Add a clean Python 3.14 manifest-only E2EE import/configuration gate.
- Validate service metadata with the real Home Assistant 2026.9.2 parser before packaging.

## 0.5.0 — 2026-09-13

Automation, rich-message, voice and location release for Home Assistant 2026.9+.

### Messaging and automation API

- Add structured `matrix_extended.send` response data with stable `delivery_id`, `sent` / `queued` status and Matrix event records.
- Add `matrix_extended_delivery` lifecycle events for `sent`, `queued`, `failed` and `dropped` deliveries.
- Add Matrix message types `text`, `notice` and `emote`.
- Add safe Markdown rendering to Matrix HTML while preserving the original Markdown body as fallback.
- Add native Matrix mentions with `mention_users` and room mentions.
- Add richer incoming payload metadata, incoming edit events and incoming redaction events.

### Reaction actions

- Persist reaction actions across Home Assistant restarts.
- Add `expires_in`, `max_uses` and `allowed_users` restrictions.
- Keep actions fail-closed: Matrix text, YAML and Jinja are never executed as arbitrary Home Assistant services.

### Voice

- Add native Matrix voice-message metadata for outgoing audio while retaining standard `m.audio` compatibility.
- Add `matrix_extended.send_voice` to synthesize text through Home Assistant TTS and send it as a Matrix voice message.
- Add `matrix_extended.transcribe_voice` to transcribe downloaded Matrix voice through a Home Assistant `stt.*` entity.
- Add OGG/Opus to WAV/PCM normalization through Home Assistant FFmpeg when required by local STT providers such as Wyoming/Whisper.
- Add explicit opt-in `assist: true` forwarding of a transcript to Home Assistant Conversation/Assist. Voice messages never execute Assist commands by default.
- Restrict voice transcription paths to the Matrix Extended incoming-media directory for the selected account.

### Location

- Add `matrix_extended.send_location` for stable Matrix `m.location` messages from explicit coordinates or a Home Assistant entity exposing latitude/longitude.
- Add incoming `matrix_extended_location` events.
- Support encrypted location delivery and location lifecycle records.

### Incoming media and retention

- Add configurable incoming-media retention by age and maximum storage size.
- Add `matrix_extended.purge_media` with response data for removed files and bytes.
- Keep cleanup confined to integration-owned incoming-media directories.

### Reliability and verification

- Extend real-stack CI to Home Assistant 2026.9.2 + Synapse 1.160.0 + Element Web 1.12.26.
- Verify a real Element recipient can decrypt Home Assistant E2EE messages.
- Verify encrypted location and native voice rendering in Element and capture real client screenshots.
- Verify persistent outbox recovery after a Synapse outage, inbound recovery, Home Assistant restart and one-shot reaction action persistence.
- Keep a verified install-ZIP gate with byte-for-byte component validation and SHA-256 checksum.

### Compatibility notes

- Existing `matrix_extended.send`, notify entities, routing profiles, replies, reactions, edits, redactions and media automations remain compatible.
- Default outgoing message type remains `text` and default format remains plain text.
- `matrix-nio==0.26.0` is retained. It does not provide Matrix cross-signing support and sends `m.reaction` unencrypted; do not use reactions for secrets.

## 0.4.2 — 2026-09-12

Reliability release validated against real Home Assistant 2026.9.2 and Synapse 1.160.0.

- Fix E2EE installation in Home Assistant environments where the built-in Matrix integration already satisfies the base `matrix-nio==0.26.0` requirement. The required E2EE runtime dependencies are now declared explicitly.
- Fix connection diagnostics during a homeserver outage by bounding matrix-nio transport retries so Matrix Extended can report the disconnect and run its own reconnect loop.
- Verify automatic inbound and encrypted outbound recovery after Synapse restart without reloading Home Assistant.
- Move matrix-nio crypto-store `restore_login()` file access out of Home Assistant's event loop.
- Add real-stack CI covering config flow, encrypted send, reload, Synapse outage/recovery, inbound recovery, Home Assistant restart, and runtime log safety.
- Add a verified release-package gate that creates the Home Assistant install ZIP only after mandatory test gates succeed, checks its contents byte-for-byte against the component tree, and publishes the archive with a SHA-256 checksum.

## 0.4.1

Baseline imported from the previously built Home Assistant install/source artifacts and preserved as the behavior reference for this release line.