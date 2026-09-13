# Matrix Extended 0.5.1 Safe Commands and Assist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, persistent Matrix command surface, camera snapshot commands, opt-in inbound voice → STT → Assist replies, progress edits, and operational diagnostics without allowing arbitrary Matrix input to become executable Home Assistant configuration.

**Architecture:** Keep parsing/persistence, execution, and automatic voice handling in focused modules. The inbound receiver remains the single Matrix authorization boundary; it delegates only already-authorized events to a command executor or voice-assist coordinator. Reuse the existing Matrix E2EE client, media resolver, TTS/STT/Conversation support, reply/edit builders, Home Assistant Store, and real-stack CI instead of creating parallel transports.

**Tech Stack:** Home Assistant 2026.9+, Python 3.13, `matrix-nio==0.26.0`, Home Assistant `Store`, Matrix E2EE, HA camera/media/TTS/STT/conversation APIs, pytest, Docker Compose, Synapse 1.160.0, Element Web 1.12.26, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-13-v051-safe-commands-assist-design.md`

## Global Constraints

- Incoming Matrix content never names an arbitrary Home Assistant service or entity at execution time.
- Account-level `allowed_users` and `allowed_rooms` must pass before command or automatic voice evaluation.
- Command-level and voice-specific allowlists may only narrow account access.
- Matching is exact after one leading `!` is removed, whitespace is collapsed, and Unicode `casefold()` is applied.
- No Jinja, YAML execution, shell execution, Python expressions, or dynamic service construction from Matrix input.
- `voice_assist_enabled` defaults to `false`.
- A failed/empty transcription never calls Assist.
- Camera commands point to a pre-registered camera entity; Matrix text cannot override it.
- Preserve all 0.5.0 behavior when commands/automatic voice Assist are disabled.
- Keep `matrix-nio==0.26.0` and Home Assistant minimum `2026.9.0`.
- Preserve existing real-stack outage/recovery/restart gates.

---

### Task 1: Persistent Safe Command Registry

**Files:**
- Create: `custom_components/matrix_extended/commands.py`
- Modify: `custom_components/matrix_extended/client.py`
- Test: `tests/test_commands_v051.py`

**Interfaces:**
- Produces: `normalize_command_phrase(value: str) -> str`
- Produces: `ServiceCommandHandler`, `CameraSnapshotCommandHandler`, `RegisteredCommand`
- Produces: `CommandRegistry.register(definition)`, `unregister(command_id)`, `match(body, sender, room_id)`, `dump()`, `async_save()`, `count`
- `MatrixAccount.command_registry` holds the per-entry registry.

- [ ] **Step 1: Write failing normalization/model tests**

```python
def test_normalize_command_phrase() -> None:
    assert normalize_command_phrase("  !Garage   OPEN  ") == "garage open"


def test_registry_rejects_duplicate_alias_across_commands() -> None:
    registry = CommandRegistry()
    registry.register({
        "id": "one",
        "trigger": "garage open",
        "aliases": ["open gate"],
        "handler": {"type": "service", "service": "script.turn_on", "target": {"entity_id": "script.open_garage"}, "data": {}},
    })
    with pytest.raises(ValueError, match="duplicate command phrase"):
        registry.register({
            "id": "two",
            "trigger": "gate open",
            "aliases": ["open gate"],
            "handler": {"type": "service", "service": "script.turn_on", "target": {"entity_id": "script.other"}, "data": {}},
        })
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_commands_v051.py`

Expected: FAIL because `commands.py` and registry types do not exist.

- [ ] **Step 3: Implement immutable command definitions and exact matching**

Core shape:

```python
@dataclass(slots=True, frozen=True)
class ServiceCommandHandler:
    service: str
    target: dict[str, Any]
    data: dict[str, Any]


@dataclass(slots=True, frozen=True)
class CameraSnapshotCommandHandler:
    entity_id: str
    caption: str


@dataclass(slots=True, frozen=True)
class RegisteredCommand:
    id: str
    trigger: str
    aliases: tuple[str, ...]
    description: str
    enabled: bool
    allowed_users: tuple[str, ...]
    allowed_rooms: tuple[str, ...]
    progress: bool
    handler: ServiceCommandHandler | CameraSnapshotCommandHandler
```

`normalize_command_phrase()` must remove only one leading `!`, trim, collapse whitespace with `" ".join(value.split())`, and `casefold()`.

`match()` rules:

```python
normalized = normalize_command_phrase(body)
if not str(body).lstrip().startswith("!"):
    return None
command_id = self._phrases.get(normalized)
command = self._items.get(command_id) if command_id else None
if command is None or not command.enabled:
    return None
if command.allowed_users and sender not in command.allowed_users:
    return None
if command.allowed_rooms and room_id not in command.allowed_rooms:
    return None
return command
```

Stored malformed entries are skipped fail-closed. Runtime registration raises a descriptive `ValueError`.

- [ ] **Step 4: Add persistence round-trip tests**

Cover service handler, camera handler, aliases, enabled, progress, per-command allowlists, malformed stored definitions, replacement by explicit identical `id`, and `unregister()`.

- [ ] **Step 5: Run GREEN**

Run: `pytest -q tests/test_commands_v051.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/commands.py custom_components/matrix_extended/client.py tests/test_commands_v051.py
git commit -m "feat: add persistent safe command registry"
```

---

### Task 2: Register/Unregister Home Assistant Actions and Store Lifecycle

**Files:**
- Create: `custom_components/matrix_extended/v051_services.py`
- Modify: `custom_components/matrix_extended/__init__.py`
- Modify: `custom_components/matrix_extended/const.py`
- Modify: `custom_components/matrix_extended/services.yaml`
- Test: `tests/test_command_services_v051.py`

**Interfaces:**
- Produces services `matrix_extended.register_command`, `matrix_extended.unregister_command`.
- `register_command` response: `{id, trigger, handler_type}`.
- `unregister_command` response: `{id, removed}`.
- Store key per config entry: `matrix_extended.commands.<entry_id>` via HA `Store`.

- [ ] **Step 1: Write failing service-schema tests**

Assert constants and `services.yaml` expose fields: `account`, `id`, `trigger`, `aliases`, `description`, `allowed_users`, `allowed_rooms`, `progress`, `handler_type`, `service`, `target`, `data`, `entity_id`, `caption`.

Test that `handler_type=service` requires `service`, forbids `entity_id`; `handler_type=camera_snapshot` requires `entity_id`, forbids service target/data.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_command_services_v051.py`

Expected: FAIL because v0.5.1 services are absent.

- [ ] **Step 3: Implement schemas and handlers**

Use one strict schema plus post-validation:

```python
_REGISTER_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ACCOUNT): cv.string,
    vol.Required("id"): cv.string,
    vol.Required("trigger"): cv.string,
    vol.Optional("aliases", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("description", default=""): cv.string,
    vol.Optional("allowed_users", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("allowed_rooms", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("progress", default=True): cv.boolean,
    vol.Required("handler_type"): vol.In(["service", "camera_snapshot"]),
    vol.Optional("service"): cv.string,
    vol.Optional("target", default={}): dict,
    vol.Optional("data", default={}): dict,
    vol.Optional("entity_id"): cv.entity_id,
    vol.Optional("caption", default="Camera snapshot"): cv.string,
}, extra=vol.PREVENT_EXTRA)
```

Persist after successful registry mutation using `await account.command_registry.async_save()`.

- [ ] **Step 4: Attach registry during config-entry setup**

In `async_setup_entry`, load `Store(hass, 1, f"{DOMAIN}.commands.{entry.entry_id}")`, instantiate `CommandRegistry(stored, store=store)`, assign `account.command_registry`, then install v0.5.1 services once.

- [ ] **Step 5: Run focused tests**

Run: `pytest -q tests/test_commands_v051.py tests/test_command_services_v051.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/v051_services.py custom_components/matrix_extended/__init__.py custom_components/matrix_extended/const.py custom_components/matrix_extended/services.yaml tests/test_command_services_v051.py
git commit -m "feat: add safe command management actions"
```

---

### Task 3: Command Execution and Progress Reply/Edit

**Files:**
- Create: `custom_components/matrix_extended/command_executor.py`
- Modify: `custom_components/matrix_extended/receiver.py`
- Modify: `custom_components/matrix_extended/const.py`
- Test: `tests/test_command_executor_v051.py`
- Test: `tests/test_receiver_v05.py`

**Interfaces:**
- Produces `CommandExecutionResult(command_id: str, status: str, handler_type: str, error: str | None)`.
- Produces `CommandExecutor.async_execute(command, *, room_id, sender, source_event_id, thread_id) -> CommandExecutionResult`.
- Receiver evaluates a command only after `_allowed()` succeeds.
- New bus event: `matrix_extended_command`.

- [ ] **Step 1: Write RED tests for exact command interception**

Test authorized `!garage open` invokes registry lookup and command executor; ordinary `hello`, unknown `!bogus`, edits, and replies that are not exact registered phrases continue to fire existing inbound events unchanged.

- [ ] **Step 2: Write RED progress lifecycle test**

Fake Matrix client should observe:

```python
pending = build_reply_content("⏳ Running…", reply_to="$command")
# handler executes
success = build_edit_content("✅ Done", event_id="$progress")
```

On exception, edit the same progress event to `❌ Failed: <sanitized summary>` and return a failed result. Truncate outbound safe error summary to 200 characters and never include traceback text.

- [ ] **Step 3: Implement command executor for service handlers**

Prepare the originating room once. For `ServiceCommandHandler`, split the stored `domain.service` and call:

```python
await hass.services.async_call(
    domain,
    service,
    dict(handler.data),
    blocking=True,
    target=dict(handler.target) or None,
)
```

No part of `event.body` enters service/domain/target/data.

- [ ] **Step 4: Wire receiver command path**

Inside `async_handle_text`, after `_allowed()` and before normal event emission, only for non-edit plain text-like events:

```python
registry = self._account.command_registry
command = registry.match(event.body, sender=event.sender, room_id=room.room_id) if registry else None
if command is not None:
    result = await self._command_executor.async_execute(...)
    self._hass.bus.async_fire(EVENT_COMMAND, {...})
    self._account.status.mark_receive()
    return
```

The event payload must include `account_id`, `room_id`, `sender`, `event_id`, `command_id`, `trigger`, `handler_type`, `status`, and bounded `error`.

- [ ] **Step 5: Run focused GREEN**

Run: `pytest -q tests/test_command_executor_v051.py tests/test_receiver_v05.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/command_executor.py custom_components/matrix_extended/receiver.py custom_components/matrix_extended/const.py tests/test_command_executor_v051.py tests/test_receiver_v05.py
git commit -m "feat: execute authorized Matrix commands"
```

---

### Task 4: Camera Snapshot Command Handler

**Files:**
- Modify: `custom_components/matrix_extended/command_executor.py`
- Modify: `custom_components/matrix_extended/media.py`
- Test: `tests/test_command_executor_v051.py`
- Test: `tests/test_media_behavior.py`

**Interfaces:**
- Consumes stored `CameraSnapshotCommandHandler.entity_id` and `.caption` only.
- Reuses `MediaResolver.async_resolve({"entity_id": ..., "type": "image"})` so the same HA camera/image path used by normal Matrix media sends is exercised.
- Sends to the originating Matrix room using the current room encryption state and `build_media_content()`.

- [ ] **Step 1: Add RED camera execution test**

Assert `!camera gate` resolves exactly the registered `camera.gate`, uploads returned JPEG bytes encrypted for an E2EE room, and sends `m.image` with the stored caption. Include a malicious-looking incoming phrase test (`!camera gate camera.other`) that does not match anything.

- [ ] **Step 2: Implement camera handler**

Pseudo-code to implement literally through existing abstractions:

```python
media = await MediaResolver(hass).async_resolve({
    "entity_id": handler.entity_id,
    "type": "image",
    "caption": handler.caption,
})
room = (await account.client.async_prepare_rooms([room_id]))[0]
upload = await account.client.async_upload(
    media.data,
    filename=media.filename,
    content_type=media.content_type,
    encrypt=room.encrypted,
)
content = build_media_content(
    media_type="image",
    mxc_uri=None if room.encrypted else upload.mxc_uri,
    encrypted_file=upload.encrypted_file if room.encrypted else None,
    filename=media.filename,
    content_type=media.content_type,
    size=len(media.data),
    caption=handler.caption,
    width=media.width,
    height=media.height,
    thread_id=thread_id,
)
await account.client.async_send_prepared([room], content)
```

- [ ] **Step 3: Verify camera errors become failed progress edits**

Cover entity missing/unavailable and media resolution failure; no exception text longer than 200 chars reaches Matrix.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_command_executor_v051.py tests/test_media_behavior.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/command_executor.py custom_components/matrix_extended/media.py tests/test_command_executor_v051.py tests/test_media_behavior.py
git commit -m "feat: add safe Matrix camera command"
```

---

### Task 5: Refactor STT/Assist into a Reusable Voice Core

**Files:**
- Modify: `custom_components/matrix_extended/voice_pipeline.py`
- Test: `tests/test_voice_pipeline_v051.py`
- Modify: `custom_components/matrix_extended/v05_services.py`

**Interfaces:**
- Produces `VoicePipelineResult(text, stt_entity, language, normalized, assist_executed, assist)`.
- Produces `async_process_voice_file(hass, account, *, path, stt_entity=None, language=None, audio_format="ogg", codec="opus", bit_rate=16, sample_rate=48000, channels=1, assist=False, conversation_agent=None, conversation_id=None) -> VoicePipelineResult`.
- Existing `matrix_extended.transcribe_voice` becomes a thin ServiceCall adapter around the reusable function.

- [ ] **Step 1: Write RED unit tests around reusable function**

Cover direct accepted OGG/Opus, ffmpeg WAV/PCM fallback, unsupported language, failed STT result, empty transcript, Assist disabled, and Assist enabled.

- [ ] **Step 2: Extract reusable core without changing service response**

The existing service response must stay byte/shape compatible:

```python
{
    "text": result.text,
    "stt_entity": result.stt_entity,
    "language": result.language,
    "normalized": result.normalized,
    "assist_executed": result.assist_executed,
    **({"assist": result.assist} if result.assist is not None else {}),
}
```

Keep `_resolve_incoming_voice_path()` as the path security boundary.

- [ ] **Step 3: Run GREEN**

Run: `pytest -q tests/test_voice_pipeline_v051.py`

Expected: PASS.

- [ ] **Step 4: Run existing regression suite**

Run: `pytest -q`

Expected: all 0.5.0 tests remain green.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/voice_pipeline.py custom_components/matrix_extended/v05_services.py tests/test_voice_pipeline_v051.py
git commit -m "refactor: expose reusable Matrix voice pipeline"
```

---

### Task 6: Automatic Inbound Voice → STT → Assist → Matrix Reply

**Files:**
- Create: `custom_components/matrix_extended/voice_assist.py`
- Modify: `custom_components/matrix_extended/receiver.py`
- Modify: `custom_components/matrix_extended/config_flow.py`
- Modify: `custom_components/matrix_extended/const.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/en.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Test: `tests/test_voice_assist_v051.py`
- Test: `tests/test_config_flow_ui_schema.py`
- Test: `tests/test_receiver_v05.py`

**Interfaces:**
- Config keys exactly: `voice_assist_enabled`, `voice_assist_stt_entity`, `voice_assist_language`, `voice_assist_conversation_agent`, `voice_assist_reply_mode`, `voice_assist_tts_entity`, `voice_assist_allowed_users`, `voice_assist_allowed_rooms`.
- Reply modes: `text`, `voice`, `both`; default `text`.
- Produces event `matrix_extended_voice_assist`.

- [ ] **Step 1: Write RED options-flow tests**

Assert options flow exposes the exact keys above, default enabled is false, reply mode selector contains only text/voice/both, and multi-value allowlists are preserved.

- [ ] **Step 2: Implement options and runtime settings**

Do not place a dynamic command editor in Options Flow. Only automatic voice settings belong here.

- [ ] **Step 3: Write RED coordinator authorization tests**

Automatic processing must return without STT/Assist when any of these is false: `voice_assist_enabled`, account inbound policy, voice-specific sender allowlist, voice-specific room allowlist, native `voice` flag, local path present and safe.

- [ ] **Step 4: Implement `VoiceAssistCoordinator`**

It receives the already-generated media payload and event metadata. Call `async_process_voice_file(..., assist=True)` only after all gates. Extract user-facing Assist speech from `assist["response"]["speech"]["plain"]["speech"]` when present; otherwise use a bounded generic success/failure response.

Text reply: use `build_reply_content()` to reply to the voice event.

Voice reply: reuse the same Home Assistant TTS generation pattern as `_async_send_voice`, but target only the originating room and mark `voice=True`.

Both: text first, voice second.

- [ ] **Step 5: Avoid blocking Matrix sync on STT latency**

After `matrix_extended_media` is fired and `local_path` is populated, schedule the coordinator with Home Assistant task creation rather than awaiting STT in the nio callback. Track errors inside the coordinator and surface them via status/event; do not let an exception escape into `sync_forever`.

- [ ] **Step 6: Run focused GREEN**

Run: `pytest -q tests/test_voice_assist_v051.py tests/test_config_flow_ui_schema.py tests/test_receiver_v05.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/matrix_extended/voice_assist.py custom_components/matrix_extended/receiver.py custom_components/matrix_extended/config_flow.py custom_components/matrix_extended/const.py custom_components/matrix_extended/strings.json custom_components/matrix_extended/translations/en.json custom_components/matrix_extended/translations/ru.json tests/test_voice_assist_v051.py tests/test_config_flow_ui_schema.py tests/test_receiver_v05.py
git commit -m "feat: add opt-in Matrix voice Assist"
```

---

### Task 7: Runtime Diagnostics for Commands, Outbox, Delivery, and E2EE

**Files:**
- Modify: `custom_components/matrix_extended/status.py`
- Modify: `custom_components/matrix_extended/sensor.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/en.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Test: `tests/test_status_v051.py`
- Test: `tests/test_sensor_v051.py`

**Interfaces:**
- Add status fields: `last_delivery_status`, `last_delivery_error`, `last_command`, `outbox_size`.
- Diagnostic sensors: `outbox_size`, `last_delivery_status`, `last_delivery_error`, `e2ee_ready`, `last_command`.
- `e2ee_ready` is derived as `connected and default_room_encrypted is True`.

- [ ] **Step 1: Write RED status listener tests**

Exercise dedicated setters and verify each notifies listeners exactly once.

- [ ] **Step 2: Implement bounded status state**

`last_delivery_error` and `last_command` strings should be bounded in sensor native value; full error may remain as an attribute following the existing `MatrixLastErrorSensor` pattern.

Update outbox size after enqueue/recovery/drop locations already present in `__init__.py`; do not poll filesystem/store.

- [ ] **Step 3: Add diagnostic sensor classes**

All new entities use `EntityCategory.DIAGNOSTIC` and the existing Matrix device.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/test_status_v051.py tests/test_sensor_v051.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/status.py custom_components/matrix_extended/sensor.py custom_components/matrix_extended/strings.json custom_components/matrix_extended/translations/en.json custom_components/matrix_extended/translations/ru.json tests/test_status_v051.py tests/test_sensor_v051.py
git commit -m "feat: add Matrix command and delivery diagnostics"
```

---

### Task 8: Real Encrypted E2E for Safe Commands, Camera, and Voice Assist

**Files:**
- Modify: `ci/scripts/prepare-ha.sh`
- Modify: `ci/scripts/ha-e2e.py`
- Modify: `ci/scripts/element-e2e.py`
- Create: `ci/scripts/matrix-command-e2e.py`
- Modify: `.github/workflows/test.yml`
- Modify: `ci/tests/test_rich_element_e2e.py`
- Test: `tests/e2e/*` only if existing helper coverage belongs there.

**Interfaces:**
- Add workflow step `Verify encrypted safe commands and automatic voice Assist` before the Synapse outage section.
- Preserve all current rich/location/voice and reconnect steps.

- [ ] **Step 1: Add RED structural CI tests**

Assert workflow contains the new command/voice step and does not remove the current real-stack recovery steps.

- [ ] **Step 2: Prepare deterministic HA test entities**

In generated HA config add an `input_boolean.matrix_command_target` and a script `matrix_command_test` that turns it on. Register command through the real `matrix_extended.register_command` action:

```yaml
id: e2e_command
trigger: test switch on
handler_type: service
service: input_boolean.turn_on
target:
  entity_id: input_boolean.matrix_command_target
progress: true
```

- [ ] **Step 3: Send the command from the human Matrix account**

`matrix-command-e2e.py` logs in using `.ci/matrix-env.json`, sends encrypted `!test switch on` to the existing E2EE room, polls HA state/API until the input boolean is `on`, then Matrix syncs until it sees the bot progress event edited to `✅ Done`.

- [ ] **Step 4: Verify unauthorized text cannot execute**

Register a second command narrowed to a non-E2E-test sender or room, send it from `@ha_user`, and assert the HA target state remains unchanged.

- [ ] **Step 5: Add deterministic camera command E2E**

Use a generated test image entity/source already consumable by `MediaResolver` in the HA test config. Register exact `!camera e2e`, send from the human Matrix account, and assert a new encrypted `m.image` from the bot is received/decrypted by the human Matrix account. If the real HA test environment cannot expose a stable camera entity without an external integration, use a test-only local custom component under `.ci/ha-config/custom_components/matrix_e2e_camera` that implements one static JPEG camera; it must exist only in generated CI config and never ship in the integration ZIP.

- [ ] **Step 6: Add deterministic voice Assist E2E**

Create a test-only local STT custom component in `.ci/ha-config/custom_components/matrix_e2e_stt` whose provider accepts WAV/PCM and returns fixed transcript `turn on matrix voice target`. Configure the built-in Home Assistant conversation agent and an intent/script path that turns on `input_boolean.matrix_voice_target`. Enable automatic voice Assist only for the E2E sender/room. Send a real native Matrix voice attachment from the human account; assert the target turns on and the bot sends an encrypted text reply.

The fake STT exists only inside disposable CI config and proves Matrix download/decrypt → audio normalization/provider → conversation → Matrix response wiring without relying on cloud STT.

- [ ] **Step 7: Run full local/CI-equivalent tests**

Run: `pytest -q`

Then run the existing Docker Compose real-stack workflow commands or push the branch and require all three jobs: fast regression, real stack, verified install ZIP.

- [ ] **Step 8: Commit**

```bash
git add ci/scripts .github/workflows/test.yml ci/tests tests/e2e
git commit -m "test: cover safe commands and voice Assist end to end"
```

---

### Task 9: 0.5.1 Documentation, Version, Changelog, and Release Gate

**Files:**
- Modify: `custom_components/matrix_extended/manifest.json`
- Modify: `README.md`
- Modify: `README.ru.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/TESTING.md`
- Modify: `ci/scripts/validate-source.py`
- Modify: `ci/tests/test_validate_source.py`
- Modify: `ci/tests/test_build_release.py`

**Interfaces:**
- Final version: `0.5.1`.
- Developer/maintainer remains `Psix-anp (@Psix-anp)` and manifest `codeowners` remains `@Psix-anp`.
- Verified package remains `matrix_extended-ha-install-v0.5.1.zip` plus SHA-256.

- [ ] **Step 1: Write RED release-contract tests**

Update validators to expect 0.5.1 and require README EN/RU mentions for `register_command`, `unregister_command`, `!camera`, automatic voice Assist opt-in, reply modes, and security restrictions.

- [ ] **Step 2: Update manifest/changelog only after feature gates are green**

Add a 0.5.1 changelog section summarizing safe commands, camera requests, automatic voice Assist, progress edits, diagnostics, and CI verification. Do not remove 0.5.0 compatibility notes.

- [ ] **Step 3: Add practical docs**

English and Russian examples must include:

```yaml
action: matrix_extended.register_command
data:
  id: garage_open
  trigger: garage open
  aliases:
    - open garage
  handler_type: service
  service: script.turn_on
  target:
    entity_id: script.open_garage
  allowed_users:
    - "@alex:example.org"
```

and:

```yaml
action: matrix_extended.register_command
data:
  id: gate_camera
  trigger: camera gate
  handler_type: camera_snapshot
  entity_id: camera.gate
  caption: Gate camera
```

Document that the user sends `!garage open` / `!camera gate`; no arbitrary arguments, service names, targets, YAML or Jinja are accepted from Matrix.

Document automatic voice settings and that they default disabled.

- [ ] **Step 4: Update testing documentation**

Document the command E2E, camera E2E, deterministic fake STT provider, and preserved outage/recovery/restart gate.

- [ ] **Step 5: Run complete verification**

Run:

```bash
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
python ci/scripts/build-release.py
```

Expected: all commands exit 0 and `dist/matrix_extended-ha-install-v0.5.1.zip` passes byte-for-byte component validation.

Then require the GitHub real-stack run to pass on the exact release head before merge.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/manifest.json README.md README.ru.md CHANGELOG.md docs/TESTING.md ci/scripts/validate-source.py ci/tests/test_validate_source.py ci/tests/test_build_release.py
git commit -m "release: prepare Matrix Extended 0.5.1"
```

---

## Self-review results

- **Spec coverage:** registry, exact matching, narrowing allowlists, service handler, camera handler, progress replies, automatic native voice STT/Assist, text/voice/both replies, diagnostics, services, options, docs, versioning, encrypted real-stack coverage are each mapped to a task.
- **Security coverage:** no runtime Matrix field can choose service/entity/target/data; all command and voice paths are downstream of account allowlists; automatic voice Assist defaults off; camera entity is stored at registration; error text is bounded.
- **Compatibility coverage:** existing manual `transcribe_voice`, send/reply/edit/media/E2EE/outbox/restart behavior remains under the full regression and real-stack gates.
- **Placeholder scan:** no implementation step depends on `TBD`, unspecified error handling, or an undefined adjacent interface.
- **Type consistency:** command registry interfaces produced in Task 1 are consumed by Tasks 2–4; reusable voice pipeline produced in Task 5 is consumed by Task 6; status interfaces produced in Task 7 are independent of execution internals.
