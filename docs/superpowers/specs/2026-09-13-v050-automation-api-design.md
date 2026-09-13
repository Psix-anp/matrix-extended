# Matrix Extended 0.5 Automation API Design

## Goal

Make Matrix Extended a stronger Home Assistant notification and automation transport without turning it into a general-purpose bot framework.

## Scope

Version 0.5 adds seven focused capabilities:

1. Delivery responses and lifecycle events for `matrix_extended.send`.
2. Matrix message types `text`, `notice`, and `emote`.
3. Native Matrix mentions (`m.mentions`).
4. Safe Markdown formatting with a plain-text fallback.
5. Inbound edit and redaction events.
6. Persistent reaction actions with expiry, per-user authorization, and bounded uses.
7. Retention and manual purge for downloaded inbound media.

Out of scope for this release: arbitrary commands parsed from Matrix text, Jinja/YAML execution from Matrix, room administration, presence/typing/read receipts, polls, location, cross-signing, Secure Backup, and experimental voice-message metadata.

## Delivery API

`matrix_extended.send` returns response data when the caller requests a response. The response shape is:

```yaml
delivery_id: 32-hex-character logical delivery id
status: sent | queued
events:
  - room_id: "!room:example.org"
    event_id: "$event:example.org"
    kind: text | media
    media_index: 0  # only for media
```

The integration fires `matrix_extended_delivery` for state transitions. Event payload:

```yaml
account_id: config-entry-id
delivery_id: logical-delivery-id
status: sent | queued | failed | dropped
events: []
error: null | string
```

`queued` is emitted once when a connection failure causes persistence into the outbox. `sent` is emitted after immediate delivery or successful outbox recovery. `failed` is emitted for an immediate permanent send failure. `dropped` is emitted when a queued delivery later fails permanently and is removed. Transient reconnect attempts do not emit repeated lifecycle events.

Stable Matrix transaction IDs continue to be derived from `delivery_id`, logical event key, and room ID so retrying a queued delivery remains idempotent.

## Message type and formatting

`send`, `reply`, and `edit` accept `msgtype` with values `text`, `notice`, or `emote`; the default remains `text` for backward compatibility. Content is emitted as `m.text`, `m.notice`, or `m.emote` respectively.

`format` accepts `text`, `html`, or `markdown`.

- `text`: no `formatted_body`.
- `html`: the provided message is used as both the plain fallback and `formatted_body`, preserving current behavior.
- `markdown`: the integration renders a deliberately small safe subset: escaped text, `**bold**`, `*italic*`, `` `code` ``, `[label](https://...)`, and line breaks. Raw HTML in Markdown is escaped. Unsupported Markdown remains readable as plain text rather than being interpreted.

No new third-party Markdown dependency is added.

## Mentions

`send` and `reply` accept:

```yaml
mention_users:
  - "@user:example.org"
mention_room: false
```

When either value is present, the event includes `m.mentions` with `user_ids` and/or `room: true`. User IDs are trimmed, deduplicated, and empty values are rejected.

For `notification_key`, mention metadata is included only when the original message is created. Replacement edits do not repeat mention metadata, preventing progress/status updates from repeatedly notifying users.

## Inbound relations

The inbound receiver adds:

- `matrix_extended_edit`
- `matrix_extended_redaction`

For an incoming replacement message (`m.relates_to.rel_type == m.replace`), the receiver fires `matrix_extended_edit` instead of `matrix_extended_message`. Payload extends the common inbound metadata with:

```yaml
replaces: "$original-event"
message: replacement body
formatted_body: replacement formatted body or null
msgtype: text | notice | emote | other
```

For a redaction, payload contains:

```yaml
redacts: "$redacted-event"
reason: optional reason
```

The common payload for inbound text/reply/edit/media/reaction gains room and sender metadata when available without any network lookup:

```yaml
room_name: string | null
canonical_alias: string | null
sender_display_name: string | null
msgtype: string | null
```

Media payload additionally exposes `size`, `width`, `height`, and `duration_ms` from Matrix `info`.

## Reaction actions v2

The existing Home Assistant Store-backed action registry remains the persistence mechanism. Each action can additionally specify:

```yaml
expires_in: 3600       # seconds, default 3600, max 604800
max_uses: 1            # default 1, range 1..100
allowed_users:
  - "@seriy:example.org"
```

The absolute expiry timestamp and remaining-use count are persisted. Expired actions are pruned on load, register, consume, and dump. If `allowed_users` is non-empty, a reaction from any other sender is ignored and does not consume a use. A matching action is removed when its remaining uses reach zero.

Security remains fail-closed: reaction actions are only evaluated after the account-level allowed-user and allowed-room policy passes, and Matrix text never becomes an arbitrary Home Assistant service call.

## Inbound media retention

New options:

- `incoming_media_retention_days`: default `7`, allowed `0..365`; `0` disables age-based cleanup.
- `incoming_media_max_mb`: default `256`, allowed `16..4096`.

Cleanup runs at setup after the account is connected and after each successful inbound-media write. Files are scoped to `/config/matrix_extended/incoming/<config_entry_id>/` only. Cleanup first deletes files older than the configured retention period, then deletes oldest remaining files until total size is at or below the configured byte cap.

New service `matrix_extended.purge_media` accepts optional `account`; it deletes downloaded inbound files only for the selected account and returns `{removed_files, removed_bytes}` when a response is requested. It never removes Matrix crypto-store, notification mappings, action registry, or outbox data.

## Compatibility and testing

- Existing YAML using `send/reply/edit` remains valid.
- `format: text|html` behavior remains compatible.
- Existing stored reaction-action entries are loaded with defaults (`expires_at` based on load time plus one hour, one remaining use, no per-action user restriction).
- Config entries receive safe defaults without requiring migration.
- Unit tests cover content builders, Markdown escaping, mentions, edit/redaction extraction, action TTL/user/use semantics, retention cleanup, and delivery result construction.
- Real-stack CI continues to validate HA 2026.9.2 + Synapse 1.160.0 and is extended to assert a service response and one `matrix_extended_delivery` event during the encrypted-send path.
