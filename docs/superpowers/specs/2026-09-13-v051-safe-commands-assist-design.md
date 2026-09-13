# Matrix Extended 0.5.1 Safe Commands and Assist Design

## Goal

Extend Matrix Extended from a secure notification transport into a small, deterministic Home Assistant control surface without turning it into a general-purpose bot framework.

Version 0.5.1 focuses on three user-facing capabilities:

1. Safe Matrix text commands backed by an explicit persistent registry.
2. Camera snapshot requests as the first specialized command handler.
3. Automatic incoming native voice -> Home Assistant STT -> Assist -> Matrix reply, with explicit opt-in.

The release also adds progress replies and diagnostic entities needed to operate these flows reliably.

## Design principles

- Fail closed. Incoming Matrix content never names an arbitrary Home Assistant service or entity at execution time.
- Reuse the account-level `allowed_users` and `allowed_rooms` policy before any command or voice-control evaluation.
- Keep the command language deliberately small and deterministic.
- Persist configured commands across Home Assistant restarts.
- Reuse existing Matrix E2EE, reply/edit, media, TTS, STT, conversation, delivery, and outbox infrastructure instead of creating parallel transports.
- Do not add Jinja, YAML execution, shell execution, Python expressions, or dynamic service construction from Matrix input.
- Preserve 0.5.0 behavior for users who do not enable commands or automatic voice Assist.

## Scope

0.5.1 includes:

- persistent safe command registry;
- exact command phrase matching with aliases;
- command-specific allowed-user and allowed-room narrowing;
- static Home Assistant service handlers;
- camera snapshot handlers;
- progress replies using one Matrix event edited from pending to success/failure;
- automatic incoming native voice transcription and optional Assist execution;
- text or TTS voice replies for Assist;
- command/voice diagnostic events and diagnostic entities;
- unit tests plus encrypted real-stack CI coverage.

Out of scope:

- arbitrary free-form service names, entity IDs, target selectors, YAML, Jinja, shell, or Python from Matrix messages;
- generic positional argument interpolation into service data;
- room administration, moderation, membership management, presence, typing indicators, read receipts, or polls;
- live location / Matrix beacon support;
- an open-ended plugin system for command handlers;
- exposing every Home Assistant entity as a Matrix command automatically.

Live location is a candidate for 0.5.2.

## Command syntax and matching

Only text events whose normalized body starts with `!` are considered commands. Normalization is:

1. trim surrounding whitespace;
2. remove exactly one leading `!`;
3. collapse internal whitespace runs to a single space;
4. Unicode `casefold()` for matching.

Registry triggers are stored without the leading `!`.

Examples:

```text
!status
!garage open
!camera gate
```

0.5.1 intentionally uses exact phrase matching rather than free-form arguments. A command can have aliases, and the complete normalized incoming phrase must match the canonical trigger or an alias.

Example definition:

```yaml
id: garage_open
trigger: garage open
aliases:
  - gate open
  - open garage
handler:
  type: service
  service: script.turn_on
  target:
    entity_id: script.open_garage
  data: {}
```

This keeps `!garage open` convenient while ensuring the Matrix sender cannot inject another service, entity, or data value.

Unknown `!` commands are ignored by default. An option may enable a short `Unknown command` reply, but the default remains quiet to avoid turning a Matrix room into a noisy parser.

## Persistent command registry

Commands are stored per Matrix config entry using Home Assistant `Store`, following the persistence model already used by reaction actions and the outbox.

A registry entry contains:

```yaml
id: stable-string-id
trigger: camera gate
aliases: []
description: Front gate snapshot
enabled: true
allowed_users: []
allowed_rooms: []
progress: true
handler:
  type: camera_snapshot
  entity_id: camera.gate
  caption: Gate camera
```

Security semantics:

- account `allowed_users` and `allowed_rooms` must pass first;
- non-empty command-level lists further narrow access and can never broaden account access;
- disabled commands never execute;
- duplicate normalized triggers/aliases are rejected;
- malformed stored entries are skipped and reported rather than executed permissively.

The registry is loaded at config-entry setup and written atomically after mutations.

## Registry management API

0.5.1 adds Home Assistant actions:

- `matrix_extended.register_command`
- `matrix_extended.unregister_command`

`register_command` accepts one complete safe definition and replaces an existing definition only when the same `id` is explicitly supplied.

Supported handler types are fixed in 0.5.1:

### `service`

Fields:

```yaml
handler_type: service
service: input_boolean.turn_on
target:
  entity_id: input_boolean.matrix_test
data: {}
```

`service`, `target`, and `data` are stored at registration time and never derived from incoming Matrix text.

### `camera_snapshot`

Fields:

```yaml
handler_type: camera_snapshot
entity_id: camera.gate
caption: Gate camera
```

The camera entity is validated when the command executes. Matrix input cannot override it.

The actions also accept:

- `account`;
- `id`;
- `trigger`;
- `aliases`;
- `description`;
- `allowed_users`;
- `allowed_rooms`;
- `progress`.

A future UI editor can write the same registry; the initial 0.5.1 implementation does not require a large dynamic command builder in Options Flow.

## Service command execution

When a registered `service` command matches:

1. common inbound allowlists pass;
2. command-level allowlists pass;
3. the integration optionally sends a progress reply;
4. the pre-registered Home Assistant service is called with the stored target/data;
5. the progress event is edited to success or failure;
6. a diagnostic event is fired.

No Matrix-provided token is interpolated into the service call.

Default progress texts are localized equivalents of:

- pending: `⏳ Running…`
- success: `✅ Done`
- failure: `❌ Failed: <safe error summary>`

A registry entry can disable progress replies for silent commands.

Error messages sent to Matrix are sanitized and bounded in length. Tracebacks and secrets remain only in Home Assistant logs.

## Camera snapshot command

`camera_snapshot` is a specialized handler because it needs media generation rather than a normal service result.

Execution flow:

1. validate the registered camera entity exists and is available;
2. request a fresh image through Home Assistant's camera API;
3. encode/send the image using the existing Matrix media path and E2EE behavior;
4. reply into the originating room, preserving thread/reply context when practical;
5. edit the optional progress event to success or failure.

The incoming phrase only selects a pre-registered command. For example `!camera gate` is itself the registered exact trigger pointing to `camera.gate`.

This avoids a separate alias-to-entity subsystem in 0.5.1.

## Automatic incoming voice -> STT -> Assist

0.5.0 already provides explicit `transcribe_voice` with optional Assist. 0.5.1 adds an automatic inbound path using the same underlying voice pipeline.

New per-account options:

```yaml
voice_assist_enabled: false
voice_assist_stt_entity: null
voice_assist_language: null
voice_assist_conversation_agent: null
voice_assist_reply_mode: text
voice_assist_tts_entity: null
voice_assist_allowed_users: []
voice_assist_allowed_rooms: []
```

`voice_assist_enabled` defaults to `false`.

The optional voice-specific allowlists narrow the normal account allowlists. They cannot broaden them.

Automatic processing occurs only when all of the following are true:

- inbound events are enabled;
- sender and room pass account allowlists;
- the event is recognized as a native Matrix voice message;
- automatic voice Assist is enabled;
- voice-specific allowlists pass when configured;
- the downloaded/decrypted file is within the integration-owned incoming-media directory.

Processing flow:

1. decrypt/download using the existing media receiver;
2. call the existing STT pipeline, including ffmpeg normalization when required;
3. if transcription succeeds and is non-empty, call `conversation.async_converse`;
4. send the result back to the same room;
5. fire a diagnostic event describing the outcome.

A failed transcription never calls Assist.

## Assist reply modes

Supported modes:

- `text`: send the Assist response as Matrix text;
- `voice`: synthesize the Assist response using the configured Home Assistant TTS entity and send native Matrix voice;
- `both`: send text plus native voice.

Default is `text` to avoid surprising TTS traffic and latency.

If `voice` or `both` is configured but TTS is unavailable, the integration falls back to text and reports the TTS failure in diagnostics rather than dropping the Assist response.

## Progress replies

Progress replies reuse the existing Matrix send/edit implementation.

A command creates one reply event and stores its Matrix event ID only for the lifetime of the execution. Completion edits that same event rather than sending multiple status messages.

This is intentionally independent from `notification_key`, whose persistence semantics target notification replacement across separate service calls.

Camera commands may finish with the image plus an edited success status. Service commands finish with the edited status only unless a later version adds explicit custom response templates.

## Diagnostic events

0.5.1 adds:

### `matrix_extended_command`

Payload:

```yaml
account_id: config-entry-id
room_id: "!room:server"
sender: "@user:server"
command_id: garage_open
trigger: garage open
handler_type: service
status: started | succeeded | failed | denied
error: null | safe-summary
```

`denied` is emitted only after the account-level inbound policy has admitted the event but a command-level restriction rejects it. Events rejected by the account allowlists remain invisible to command processing.

### `matrix_extended_voice_assist`

Payload:

```yaml
account_id: config-entry-id
room_id: "!room:server"
sender: "@user:server"
status: transcribed | succeeded | failed | denied
transcript: null | string
conversation_id: null | string
error: null | safe-summary
```

No access tokens, decrypted media bytes, or tracebacks are included.

## Diagnostic entities

New entities are `entity_category: diagnostic` and disabled by default unless stated otherwise:

- `sensor.<account>_outbox_size` — enabled by default because pending deliveries are operationally useful;
- `binary_sensor.<account>_e2ee_ready` — disabled by default;
- `sensor.<account>_last_command` — disabled by default;
- `sensor.<account>_last_delivery_status` — disabled by default.

`last_command` attributes may expose command ID, sender, room, handler type, and status, but not full raw Matrix event content.

Existing `last_send`, `last_error`, and `last_receive` entities remain compatible.

## Security invariants

The following are hard release requirements:

1. Matrix text cannot choose a service name at runtime.
2. Matrix text cannot choose an entity ID at runtime.
3. Matrix text cannot provide arbitrary service data.
4. No Jinja, YAML, shell, Python expression, or template evaluation is performed on incoming text.
5. Account allowlists always run before command or automatic voice processing.
6. Command/voice-specific allowlists can only narrow access.
7. Automatic voice Assist is opt-in and disabled by default.
8. Voice processing only reads integration-owned incoming media paths.
9. Camera commands can access only the entity stored in their registry definition.
10. Failure replies never expose tokens, filesystem secrets, or tracebacks.

## Compatibility and migration

- 0.5.0 config entries remain valid without migration input from the user.
- New options receive safe defaults, with commands and automatic voice Assist disabled unless configured.
- Existing inbound message/media/reaction events keep their current behavior.
- A message beginning with `!` still produces the normal inbound message event; command evaluation is an additional controlled path when a matching command exists.
- Existing explicit `transcribe_voice` remains available and unchanged.
- Existing reaction actions are independent from the text-command registry.

## Testing strategy

### Unit tests

Cover:

- command normalization and exact matching;
- duplicate trigger/alias rejection;
- registry persistence and malformed-entry handling;
- account + command allowlist intersection;
- service handler uses only stored service/target/data;
- no Matrix token interpolation into service calls;
- camera handler uses only the stored camera entity;
- progress send -> edit lifecycle;
- automatic voice opt-in and allowlist behavior;
- STT failure prevents Assist;
- text/voice/both reply modes and TTS fallback;
- diagnostic event/entity state updates.

### Real Home Assistant + Synapse + Element CI

Extend the existing disposable encrypted stack with one safe service command:

1. define a harmless Home Assistant test entity/helper;
2. register a command whose static handler changes that helper;
3. send the encrypted command from the Matrix test user;
4. verify Home Assistant state changed;
5. verify Element decrypts the progress/success reply;
6. restart Home Assistant and verify the command registry still works.

The existing E2EE text, location, voice, outbox outage/recovery, restart, and package gates remain mandatory.

Camera snapshot gets unit/integration coverage against Home Assistant's camera API. It is added to the full Element E2E path only if a deterministic built-in/local camera fixture can be provided without external network dependencies.

Automatic voice Assist gets a real-stack test only with deterministic local STT/Conversation fixtures; otherwise the CI contract verifies receiver routing and uses controlled Home Assistant test doubles while the existing native voice render remains real Element E2E.

## Release acceptance criteria

0.5.1 is releasable when:

- all 0.5.0 regression and real-stack gates remain green;
- commands persist across Home Assistant restart;
- an encrypted Matrix command can execute only its pre-registered static HA action;
- unauthorized users/rooms cannot execute it;
- camera snapshot commands cannot target arbitrary entities;
- automatic voice Assist remains disabled by default;
- enabled voice Assist respects all allowlists and never executes on failed STT;
- progress replies update one event rather than spamming status messages;
- diagnostic entities/events contain no secrets;
- documentation includes EN/RU setup and safe examples for commands, camera, and voice Assist.
