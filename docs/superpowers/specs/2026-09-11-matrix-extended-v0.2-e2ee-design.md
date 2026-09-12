# Matrix Extended v0.2 E2EE Design

## Goal

Add real Matrix E2EE to outbound Home Assistant notifications without bloating the integration, while also exposing useful account health entities.

## Security model

- TLS protects HA-to-homeserver transport when HTTPS and certificate verification are enabled.
- Matrix encrypted rooms use `matrix-nio` Olm/Megolm state persisted across HA restarts.
- Text events use nio's transparent room encryption.
- Attachments and thumbnails use nio encrypted uploads and Matrix `file` / `thumbnail_file` metadata, so the homeserver stores ciphertext.
- `Require E2EE` defaults to true and blocks plaintext target rooms before any media upload.
- v0.2 allows unverified recipient devices because matrix-nio lacks cross-signing support; strict verified-device enforcement is intentionally deferred.

## Persistent state

A per-config-entry crypto store lives under `/config/.storage/matrix_extended/<entry_id>`. A generated store key is stored in the Home Assistant config entry. Existing v0.1 entries receive both the E2EE policy and store key automatically at setup.

## Outbound flow

1. Resolve target rooms and sync key/device state.
2. Reject any plaintext room when `Require E2EE` is true.
3. Send text via `room_send`; nio encrypts encrypted rooms.
4. Resolve each media item once in HA.
5. Group targets by encryption state.
6. For encrypted groups, upload media and thumbnails with `encrypt=True` and build `file`/`thumbnail_file` content.
7. For plaintext groups (only when policy explicitly permits), use ordinary MXC `url` fields.
8. Update shared runtime health state.

## Entities

- connection binary sensor;
- user ID;
- device ID;
- default room;
- default-room encryption state;
- last successful send;
- last error.

These are diagnostic entities. Connection is last-known state rather than an active poller.

## Deliberate exclusions

Inbound events, commands, reactions, edits/redactions, cross-signing, SAS UI, key backup and video probing remain out of scope for v0.2.
