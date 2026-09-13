# Changelog

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

- Add `matrix_extended.send_location` for stable Matrix `m.location` messages from explicit coordinates or Home Assistant entities exposing latitude/longitude.
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
- Add a fast source/compile/regression gate; current release branch has 149 passing tests.
- Add a verified release-package gate that creates the Home Assistant install ZIP only after both mandatory test gates succeed, checks its contents byte-for-byte against the component tree, and publishes the archive with a SHA-256 checksum.

## 0.4.1

Baseline imported from the previously built Home Assistant install/source artifacts and preserved as the behavior reference for this release line.
