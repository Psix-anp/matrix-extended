# Matrix Extended — connection and settings

**English** · [Русский](SETTINGS.ru.md)

Matrix Extended is configured from the Home Assistant UI. YAML is not required to add or configure the integration.

## Before you start

You need:

- a working Matrix homeserver reachable from Home Assistant;
- a Matrix account for the integration;
- a Matrix room the account has joined;
- Home Assistant 2026.9.0 or newer.

A dedicated Matrix account is recommended when you enable incoming automations, safe commands or automatic Voice Assist.

## First connection

Open **Settings → Devices & services → Add integration → Matrix Extended**.

The initial form contains these fields:

| UI field | Internal key | Default | Explanation |
| --- | --- | --- | --- |
| Homeserver | `homeserver` | — | Matrix Client API base URL such as `https://matrix.example.org` |
| Matrix user ID | `user_id` | — | Full Matrix ID such as `@homeassistant:example.org` |
| Password | `password` | — | Used only to perform the initial Matrix login; the integration does not store this password |
| Default room | `default_room` | — | Room ID (`!...`) or alias (`#...`) used when an action does not provide a target/route |
| Verify TLS certificate | `verify_ssl` | `true` | Validate the homeserver TLS certificate |
| Require E2EE | `require_e2ee` | `true` | Refuse outbound delivery to plaintext rooms |
| Enable incoming events | `incoming_enabled` | `true` | Start inbound Matrix processing |
| Allowed users | `allowed_users` | empty in form | Sender allowlist. If empty during initial setup, the logged-in Matrix user is inserted automatically |
| Allowed rooms | `allowed_rooms` | empty in form | Room allowlist. If empty during initial setup, `default_room` is inserted automatically |
| Download incoming media | `download_incoming_media` | `true` | Download/decrypt admitted Matrix media so automations can use local files |

### What happens when you submit

1. Matrix Extended logs in with the supplied Matrix ID and password.
2. The password is exchanged for a Matrix access token and device ID. The password itself is not persisted by the integration.
3. `default_room` is validated. A Room ID beginning with `!` is accepted directly; an alias beginning with `#` is resolved through the homeserver.
4. A duplicate `homeserver + user_id` config entry is rejected.
5. If the initial user/room allowlists were left empty, they are initialized to the logged-in user and default room respectively.
6. The access token, device ID, connection/security settings and a generated local store key are saved in the Home Assistant config entry.
7. Matrix Extended initializes its persistent E2EE state and runtime connection.

If login fails, Home Assistant reports an authentication error. If the homeserver cannot be reached, it reports a connection error. An invalid room/alias is shown on the room field.

## Where to configure it later

Open **Settings → Devices & services → Matrix Extended → Configure**.

The options menu has five sections:

1. **General**
2. **Incoming & security**
3. **Incoming media**
4. **Voice Assist**
5. **Notification routes**

## General

### Default room — `default_room`

Room ID (`!...`) or alias (`#...`) used when an action does not specify `target` or `route`. A changed alias is validated/resolved before the setting is accepted.

Matrix Extended also exposes a **Default room** select entity populated from joined rooms; changing the select persists the new default.

### Verify TLS certificate — `verify_ssl`

Default: `true`.

Keep enabled for normal HTTPS homeservers. Disable only when you intentionally use a trusted local/test server with a certificate Home Assistant cannot verify.

Changing `default_room` or `verify_ssl` updates the connection settings used by the runtime.

### Require E2EE — `require_e2ee`

Default: `true`.

When enabled, Matrix Extended refuses outbound delivery to plaintext target rooms. Disabling it permits plaintext rooms; it does not disable encryption in rooms that are already encrypted.

## Incoming & security

### Enable incoming events — `incoming_enabled`

Default: `true` after initial setup.

Controls the inbound Matrix receiver. When enabled, both allowlists below must contain at least one value.

### Allowed users — `allowed_users`

Matrix user IDs allowed to reach Home Assistant, for example:

```text
@seriy:example.org
@family:example.org
```

### Allowed rooms — `allowed_rooms`

Matrix Room IDs/allowed room identifiers from which inbound events are accepted, for example:

```text
!abcdef:example.org
```

Incoming handling is **fail-closed**. An event is processed only when both its sender and room pass the account-level inbound policy. Own transaction echoes are ignored.

This policy applies before incoming messages, media, reactions, safe commands and automatic Voice Assist are processed.

## Incoming media

### Download and decrypt incoming media — `download_incoming_media`

Default: `true`.

When enabled, admitted Matrix image/video/audio/file events are downloaded and decrypted for local automation use. `matrix_extended_media` exposes the saved path as `local_path` and any failure as `download_error`.

Files are isolated per Matrix Extended config entry:

```text
/config/matrix_extended/incoming/<config_entry_id>/
```

The actual prefix is based on Home Assistant's config directory through `hass.config.path(...)`, so unusual installations may not literally use `/config`.

### Retention, days — `incoming_media_retention_days`

Range: `0`…`365` days.

Age-based cleanup for downloaded incoming media. `0` disables age-based expiry. Quota cleanup can still apply.

### Storage limit, MiB — `incoming_media_max_mb`

Range: `16`…`4096` MiB.

Bounds the integration-owned incoming-media directory. Cleanup is scoped to Matrix Extended's own directory. `matrix_extended.purge_media` performs an immediate manual purge and can return removed file/byte counts.

## Voice Assist — `voice_assist`

Automatic Voice Assist is **disabled by default**. It is separate from the manual `matrix_extended.transcribe_voice` action.

The automatic pipeline runs only after all of these conditions are true:

- account-level incoming policy already allowed the sender and room;
- Voice Assist is enabled;
- the event is a native Matrix voice message;
- the media was downloaded successfully and has a `local_path`;
- optional Voice Assist user/room restrictions also allow the event.

### Enable automatic Voice Assist — `voice_assist_enabled`

When enabled, eligible Matrix voice messages are sent through Home Assistant STT and then Conversation/Assist.

### STT entity — `voice_assist_stt_entity`

Optional `stt.*` entity. If omitted, Home Assistant's default STT engine is used.

### Language — `voice_assist_language`

Optional recognition/Assist language. If omitted, the pipeline falls back according to the selected provider/Home Assistant language behavior.

### Conversation agent — `voice_assist_conversation_agent`

Optional `conversation.*` entity. If omitted, Home Assistant's default conversation agent is used.

### Reply mode — `voice_assist_reply_mode`

Values:

- `text` — reply to the original Matrix voice event with Assist speech as text;
- `voice` — synthesize the Assist speech through Home Assistant TTS and send native Matrix voice;
- `both` — send both text and voice.

Default: `text`.

If `voice`/`both` TTS fails, Matrix Extended falls back to a text reply when necessary and records a sanitized Voice Assist error.

### TTS entity — `voice_assist_tts_entity`

Optional `tts.*` entity used for `voice` or `both` replies. If omitted, Home Assistant TTS resolution is used.

### Voice Assist allowed users — `voice_assist_allowed_users`

Optional additional sender restriction. An empty list adds no extra restriction; the account-level `allowed_users` still applies.

### Voice Assist allowed rooms — `voice_assist_allowed_rooms`

Optional additional room restriction. An empty list adds no extra restriction; the account-level `allowed_rooms` still applies.

Use these fields to narrow Voice Assist to the smallest trusted set. They never widen the account-level inbound allowlists.

Automatic Voice Assist emits `matrix_extended_voice_assist` lifecycle events with `succeeded`/`failed`, sender, room, transcript/conversation ID when available, and a sanitized error when applicable.

## Notification routes

Routes are reusable names for one or more Matrix rooms. They are managed graphically with **Add route**, **Edit route**, and **Delete route**.

Example:

```text
security → !garage:example.org, !gate:example.org
```

Then an action can use:

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Alarm"
```

A route name must not be empty and must contain at least one room. `route` and explicit `target` are mutually exclusive.

## Safe Matrix commands

Safe commands are managed with `matrix_extended.register_command` / `matrix_extended.unregister_command`. They are not arbitrary chat-to-service execution.

The incoming Matrix text only selects an already stored command; its Home Assistant service/target/data or camera entity are fixed at registration time. Account-level incoming allowlists apply first, and each command can further restrict `allowed_users` and `allowed_rooms`.

Both supported handler modes and ready-to-copy examples are documented in [EXAMPLES.md](EXAMPLES.md#11-matrix_extendedregister_command--safe-commands).

## Persistent data

Matrix Extended keeps access/device information in the Home Assistant config entry and E2EE/registry data under Home Assistant storage. The crypto-state directory is under:

```text
/config/.storage/matrix_extended/<config_entry_id>/
```

Do not manually edit Home Assistant storage while Home Assistant is running, and do not publish config-entry data, access tokens, crypto stores or Authorization headers in bug reports.

## Diagnostics

The integration device exposes diagnostics including:

- connection state;
- Matrix user/device IDs;
- default room and encryption state;
- last successful send;
- last incoming event and type-specific metadata;
- last error;
- command/delivery-related runtime state where applicable.

For action fields and response data see [ACTIONS.md](ACTIONS.md). For complete automations see [EXAMPLES.md](EXAMPLES.md).
