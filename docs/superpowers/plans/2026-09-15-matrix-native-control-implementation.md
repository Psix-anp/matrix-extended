# Matrix Native Control 0.6.0b1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `0.6.0b1` Native Matrix Control: one maintained control panel per existing Matrix room, live HA state rendering, reaction-driven safe actions, two-step confirmation for dangerous actions, persistence/recovery, GUI configuration, diagnostics, and real-stack release validation.

**Architecture:** Keep Home Assistant as the source of truth. Panel configuration lives in `config_entry.options`; runtime root-event metadata lives in `Store`; pending confirmations are memory-only and are always discarded on reload/restart. Matrix reactions, existing safe commands, and future Widget actions all normalize to one safe action execution core. Panel state changes are event-driven, debounced, and emitted as `m.replace` edits of a stable root event.

**Tech Stack:** Home Assistant 2026.9.x custom integration APIs, Python 3.13/3.14, `matrix-nio[e2e]==0.26.0`, Synapse 1.160.0, Element Web 1.12.26, pytest 9, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-matrix-native-control-design.md`

## Global Constraints

- `0.6.0b1` uses existing Matrix rooms only; no automatic Space/room creation.
- Account-level `allowed_users` and `allowed_rooms` are the outer fail-closed boundary; panel rules may only narrow access.
- Matrix events never provide arbitrary executable `domain.service` payloads; they reference preconfigured actions.
- Home Assistant state is authoritative; do not optimistically mutate panel state after a service call.
- One panel per Matrix room for `0.6.0b1`.
- Panel updates use HA state subscriptions, not polling.
- Default panel debounce is 1.5 seconds.
- Dangerous-action confirmation expires after 30 seconds and only the same Matrix sender may confirm.
- Pending confirmations are never persisted and are dropped on reload/restart.
- Root loss/redaction moves a panel to `needs_repair`; do not create roots in a retry loop.
- Pinning is best-effort. Missing Matrix power level is diagnostic-only and must not disable control.
- Preserve existing E2EE behavior and `matrix-nio[e2e]==0.26.0`.
- Real-stack release gate remains Home Assistant 2026.9.2 + Synapse 1.160.0 + Element 1.12.26 plus Python 3.14 manifest runtime.
- `0.6.0b1` GitHub Release is a Pre-release, with bilingual notes, exact commit, verified ZIP and SHA256.

---

## File Structure

New focused modules:

- `custom_components/matrix_extended/safe_actions.py` — pure action dataclasses, validation and normalization shared by commands/reactions/panels.
- `custom_components/matrix_extended/safe_action_executor.py` — Home Assistant execution and bounded secret-redacted results.
- `custom_components/matrix_extended/control_panels.py` — pure panel configuration dataclasses, validation and YAML serialization helpers.
- `custom_components/matrix_extended/control_panel_render.py` — pure HA-state-to-Matrix panel rendering and hashing.
- `custom_components/matrix_extended/control_panel_runtime.py` — persistent root metadata and in-memory confirmation registry.
- `custom_components/matrix_extended/control_panel_manager.py` — panel lifecycle, state subscriptions, debounce, Matrix writes, action routing, pin/repair logic and diagnostics snapshots.

Existing modules changed:

- `actions.py` — persist reaction actions as shared safe-action definitions.
- `commands.py` — normalize command handlers through shared safe-action definitions.
- `command_executor.py` — keep Matrix progress/reply presentation but delegate HA execution.
- `client.py` — add room-event/state helpers needed for root validation and pinning.
- `content.py` — allow panel metadata to survive root/edit rendering.
- `receiver.py` — route panel reactions/redactions and reuse the shared action executor.
- `__init__.py` — construct/start/stop panel manager and listener ownership.
- `config_flow.py`, `const.py`, `strings.json`, `translations/ru.json` — graphical panel CRUD/import/export.
- `sensor.py` — panel diagnostic sensor.
- `README.md`, `README.ru.md`, `docs/*` — user documentation.
- `ci/scripts/*`, `.github/workflows/test.yml`, `.github/workflows/release.yml` — real-stack panel test and beta release semantics.

---

### Task 1: Shared Safe Action Model and Executor

**Files:**
- Create: `custom_components/matrix_extended/safe_actions.py`
- Create: `custom_components/matrix_extended/safe_action_executor.py`
- Modify: `custom_components/matrix_extended/actions.py`
- Modify: `custom_components/matrix_extended/commands.py`
- Modify: `custom_components/matrix_extended/command_executor.py`
- Test: `tests/test_safe_actions_v060.py`
- Test: `tests/test_commands_v051.py`
- Test: `tests/test_command_executor_v051.py`
- Test: `tests/test_reaction_actions.py` if present; otherwise add coverage to `tests/test_safe_actions_v060.py`

**Interfaces:**
- Produces `ServiceActionHandler(service: str, target: dict[str, Any], data: dict[str, Any])`.
- Produces `CameraSnapshotActionHandler(entity_id: str, caption: str)`.
- Produces `SafeActionDefinition(id: str, handler: ServiceActionHandler | CameraSnapshotActionHandler, confirmation_required: bool = False)`.
- Produces `SafeActionExecutionResult(action_id: str, status: str, handler_type: str, error: str | None)`.
- Produces `SafeActionExecutor.async_execute(action: SafeActionDefinition) -> SafeActionExecutionResult`.
- Existing `CommandExecutor` remains the Matrix progress adapter and delegates HA execution to `SafeActionExecutor`.

- [ ] **Step 1: Write failing pure-model tests**

```python
from custom_components.matrix_extended.safe_actions import (
    SafeActionDefinition,
    ServiceActionHandler,
    parse_service_handler,
)


def test_service_handler_rejects_invalid_service():
    with pytest.raises(ValueError, match="domain.service"):
        parse_service_handler({"service": "broken"})


def test_safe_action_keeps_only_preconfigured_payload():
    action = SafeActionDefinition(
        id="garage.open",
        handler=ServiceActionHandler(
            service="cover.open_cover",
            target={"entity_id": "cover.garage"},
            data={},
        ),
        confirmation_required=True,
    )
    assert action.id == "garage.open"
    assert action.handler.service == "cover.open_cover"
    assert action.confirmation_required is True
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_safe_actions_v060.py`

Expected: FAIL because `safe_actions.py` does not exist.

- [ ] **Step 3: Implement the pure action model**

Create `safe_actions.py` with frozen/slotted dataclasses and shared validators. Keep Matrix sender/room authorization out of this file.

```python
@dataclass(slots=True, frozen=True)
class ServiceActionHandler:
    service: str
    target: dict[str, Any]
    data: dict[str, Any]


@dataclass(slots=True, frozen=True)
class CameraSnapshotActionHandler:
    entity_id: str
    caption: str


@dataclass(slots=True, frozen=True)
class SafeActionDefinition:
    id: str
    handler: ServiceActionHandler | CameraSnapshotActionHandler
    confirmation_required: bool = False
```

Implement `parse_service_handler()`, `parse_camera_snapshot_handler()`, `handler_type()` and JSON-safe dump helpers. Reuse the current validation semantics from `commands.py` rather than inventing new accepted shapes.

- [ ] **Step 4: Write executor RED tests**

Use a fake `hass.services.async_call` and assert blocking execution plus bounded secret redaction.

```python
result = await SafeActionExecutor(hass).async_execute(action)
assert result.status == "success"
hass.services.async_call.assert_awaited_once_with(
    "cover", "open_cover", {}, blocking=True,
    target={"entity_id": "cover.garage"},
)
```

Also assert an exception containing `token=abc123` is returned with `token=<redacted>`.

- [ ] **Step 5: Implement `SafeActionExecutor`**

Move the reusable HA service-call and `_safe_error()` behavior out of `command_executor.py`. Keep camera snapshot execution as a supported bounded handler using the current `MediaResolver` + Matrix upload path through an optional execution context when required; do not regress the existing camera command.

- [ ] **Step 6: Migrate commands and reaction actions**

`RegisteredCommand.handler` should be convertible to `SafeActionDefinition` without changing its public stored schema. `ReactionActionRegistry.consume()` should return a shared service action definition or an adapter object convertible to one. Do not change existing persisted Store format in this task.

- [ ] **Step 7: Make `CommandExecutor` delegate**

Keep progress-message creation/editing in `command_executor.py`, but replace its direct `hass.services.async_call()` path with `SafeActionExecutor`. Preserve current `CommandExecutionResult` compatibility for existing sensors/events.

- [ ] **Step 8: Run focused and existing tests**

Run:

```bash
pytest -q tests/test_safe_actions_v060.py \
  tests/test_commands_v051.py \
  tests/test_command_executor_v051.py \
  tests/test_camera_command_v051.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add custom_components/matrix_extended/safe_actions.py \
  custom_components/matrix_extended/safe_action_executor.py \
  custom_components/matrix_extended/actions.py \
  custom_components/matrix_extended/commands.py \
  custom_components/matrix_extended/command_executor.py tests/
git commit -m "refactor: unify safe Matrix action execution"
```

---

### Task 2: Pure Control Panel Configuration and YAML Import/Export

**Files:**
- Create: `custom_components/matrix_extended/control_panels.py`
- Modify: `custom_components/matrix_extended/const.py`
- Test: `tests/test_control_panels_v060.py`

**Interfaces:**
- Produces `PanelEntity(entity_id: str, label: str)`.
- Produces `PanelAction(id: str, reaction: str, label: str, action: SafeActionDefinition)`.
- Produces `ControlPanelDefinition(panel_id, room, title, enabled, entities, actions, allowed_users, debounce)`.
- Produces `normalize_control_panels(raw, *, account_allowed_users, account_allowed_rooms) -> dict[str, ControlPanelDefinition]`.
- Produces `dump_panel_yaml(panel) -> str` and `load_panel_yaml(text, *, account_allowed_users, account_allowed_rooms) -> ControlPanelDefinition`.

- [ ] **Step 1: Write validation RED tests**

Cover:

```python
def test_rejects_two_panels_in_same_room(): ...
def test_rejects_duplicate_action_id(): ...
def test_rejects_duplicate_reaction_key(): ...
def test_panel_users_must_be_subset_of_account_allowlist(): ...
def test_panel_room_must_be_in_account_allowlist(): ...
def test_debounce_defaults_to_1_5_seconds(): ...
```

Use exact example data from the design spec.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_control_panels_v060.py`

Expected: FAIL because the module is missing.

- [ ] **Step 3: Implement panel dataclasses and normalization**

Use deterministic tuples for entities/actions and a dictionary keyed by `panel_id`. Normalize Matrix room/user strings but do not resolve aliases here; alias resolution stays in runtime setup.

Reject:
- empty `panel_id`;
- duplicate panel ID;
- duplicate room;
- empty entity list;
- duplicate entity ID;
- duplicate action ID;
- duplicate reaction;
- panel users outside account user allowlist;
- panel room outside account room allowlist;
- debounce outside `0.25..10.0` seconds.

- [ ] **Step 4: Add YAML round-trip tests**

```python
yaml_text = dump_panel_yaml(panel)
loaded = load_panel_yaml(
    yaml_text,
    account_allowed_users={"@owner:matrix.test"},
    account_allowed_rooms={"!room:matrix.test"},
)
assert loaded == panel
```

Also reject multi-document YAML and non-mapping roots. Use `yaml.safe_load` / `yaml.safe_dump`; Home Assistant already provides PyYAML at runtime, and tests should import it only through the integration helper.

- [ ] **Step 5: Add constants**

Add `CONF_CONTROL_PANELS = "control_panels"` and the field keys used by Options Flow. Keep names stable because they become persisted options schema.

- [ ] **Step 6: Run tests**

Run: `pytest -q tests/test_control_panels_v060.py tests/test_config_flow_ui_schema.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/matrix_extended/control_panels.py \
  custom_components/matrix_extended/const.py tests/test_control_panels_v060.py
git commit -m "feat: add validated Matrix control panel definitions"
```

---

### Task 3: Matrix Event/State Transport for Roots and Pins

**Files:**
- Modify: `custom_components/matrix_extended/client.py`
- Modify: `custom_components/matrix_extended/content.py`
- Test: `tests/test_client_control_state_v060.py`
- Test: `tests/test_content.py`

**Interfaces:**
- Produces `MatrixClient.async_get_event(room: str, event_id: str) -> Mapping[str, Any] | None`.
- Produces `MatrixClient.async_get_state_event(room: str, event_type: str, state_key: str = "") -> Mapping[str, Any] | None`.
- Produces `MatrixClient.async_put_state_event(room: str, event_type: str, content: dict[str, Any], state_key: str = "") -> str | None`.
- Produces `MatrixClient.async_pin_event(room: str, event_id: str) -> bool`; merges `m.room.pinned_events` and preserves unrelated pins.
- Produces panel-aware text/edit builders that keep `io.psix.matrix_extended.panel` in both root content and `m.new_content`.

- [ ] **Step 1: Write RED tests for pin merging**

```python
existing = {"pinned": ["$foreign"]}
await client.async_pin_event("!room:test", "$panel")
assert fake_nio.room_put_state.await_args.kwargs["content"] == {
    "pinned": ["$foreign", "$panel"]
}
```

Also assert pinning an already pinned event performs no state write.

- [ ] **Step 2: Implement room state helpers**

Wrap matrix-nio `room_get_state_event`, `room_put_state`, and `room_get_event`. Convert Matrix error responses to existing `MatrixSendError`/`MatrixConnectionError` categories. `404`/missing root may return `None` only when it semantically means the event is unavailable; authorization/transport failures remain errors.

- [ ] **Step 3: Write RED tests for panel metadata**

Assert root content includes:

```python
"io.psix.matrix_extended.panel": {"schema": 1, "panel_id": "garage"}
```

and an `m.replace` event keeps the same marker inside `m.new_content`.

- [ ] **Step 4: Extend content builders**

Prefer an optional `extra_content: Mapping[str, Any] | None` parameter on `build_text_content()` and `build_edit_content()` instead of creating duplicate message builders. Apply extra fields to the visible root content and the edit's `m.new_content`; do not allow callers to overwrite `msgtype`, `body`, `m.relates_to`, or `m.new_content`.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest -q tests/test_client_control_state_v060.py tests/test_content.py tests/test_client_e2ee.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/client.py \
  custom_components/matrix_extended/content.py \
  tests/test_client_control_state_v060.py tests/test_content.py
git commit -m "feat: add Matrix panel state and pin transport"
```

---

### Task 4: Deterministic Panel Renderer and Render Hash

**Files:**
- Create: `custom_components/matrix_extended/control_panel_render.py`
- Test: `tests/test_control_panel_render_v060.py`

**Interfaces:**
- Produces `RenderedPanel(body: str, formatted_body: str, digest: str)`.
- Produces `render_control_panel(panel: ControlPanelDefinition, states: Mapping[str, Any]) -> RenderedPanel`.
- Rendering must not include the current wall-clock timestamp in the digest; otherwise unchanged HA state would cause useless edits.

- [ ] **Step 1: Write RED tests for domain rendering**

Cover at least:

```python
("light.garage", "on", "On")
("cover.garage", "closed", "Closed")
("cover.garage", "opening", "Opening")
("alarm_control_panel.home", "armed_away", "Armed away")
("sensor.temp", "18.7", "18.7 °C")
("unknown.foo", "mystery", "mystery")
```

Use fake state objects with `.state` and `.attributes`.

- [ ] **Step 2: Test output structure and HTML escaping**

Assert action legend order follows configured action order and labels/states such as `<Garage>` render escaped HTML while plain body remains readable.

- [ ] **Step 3: Implement renderer**

Use small domain-aware helpers (`_render_binary`, `_render_cover`, `_render_alarm`, `_render_climate`, `_render_sensor`) and a raw fallback. Include unit of measurement when present. Do not add Jinja/template evaluation.

Digest input should be the stable UTF-8 combination of `body` plus `formatted_body`; use SHA256 hex.

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_control_panel_render_v060.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/control_panel_render.py \
  tests/test_control_panel_render_v060.py
git commit -m "feat: render Matrix control panels from HA state"
```

---

### Task 5: Runtime Store and Same-Sender Confirmation Registry

**Files:**
- Create: `custom_components/matrix_extended/control_panel_runtime.py`
- Test: `tests/test_control_panel_runtime_v060.py`

**Interfaces:**
- Produces `PanelRuntime(panel_id, room_id, root_event_id, render_hash, generation, pin_status, pin_error, needs_repair, last_update_at, last_update_error)`.
- Produces `ControlPanelRuntimeStore.restore()/dump()/async_save()` adapter around HA `Store` data.
- Produces `PendingConfirmationRegistry.issue(...)`, `.consume(...)`, `.cancel(...)`, `.count`, `.clear()`.
- Confirmation key is the confirmation prompt `event_id`, not just emoji/action ID.

- [ ] **Step 1: Write persistence RED tests**

Assert JSON-safe round trip preserves root ID, generation, pin state and repair state but contains no pending confirmations.

- [ ] **Step 2: Write confirmation RED tests**

Cover:

```python
def test_confirmation_same_sender_succeeds(): ...
def test_confirmation_other_sender_does_not_consume(): ...
def test_confirmation_expires_after_30_seconds(): ...
def test_confirmation_wrong_generation_is_stale(): ...
def test_confirmation_cannot_be_replayed(): ...
def test_clear_drops_all_pending_on_reload(): ...
```

Inject a clock callback for deterministic expiry tests.

- [ ] **Step 3: Implement runtime models**

Use a monotonically increasing integer `generation` for each new root. Any new root invalidates old prompt confirmations.

- [ ] **Step 4: Implement memory-only confirmation registry**

Store `prompt_event_id`, `panel_id`, `action_id`, `sender`, `generation`, `expires_at`. `consume()` removes a valid confirmation atomically; unauthorized sender leaves it available for the authorized sender until expiry.

- [ ] **Step 5: Run tests**

Run: `pytest -q tests/test_control_panel_runtime_v060.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/control_panel_runtime.py \
  tests/test_control_panel_runtime_v060.py
git commit -m "feat: persist Matrix panel runtime and confirmations"
```

---

### Task 6: Control Panel Manager Lifecycle, Debounce, Root Creation, Pinning and Repair

**Files:**
- Create: `custom_components/matrix_extended/control_panel_manager.py`
- Modify: `custom_components/matrix_extended/client.py` only if a narrowly required helper is missing
- Test: `tests/test_control_panel_manager_v060.py`

**Interfaces:**
- Produces `ControlPanelManager.async_start()`, `async_stop()`, `async_handle_reaction(...)`, `async_handle_redaction(...)`, `async_repair(panel_id)`, `diagnostics_snapshot()`, `add_listener()`.
- Consumes panel definitions, `SafeActionExecutor`, runtime Store, account Matrix client and account incoming policy.
- Exposes latest desired render in memory so Matrix outages coalesce state changes instead of feeding the persistent general-message outbox.

- [ ] **Step 1: Write RED test for one root and action reactions**

Fake Matrix client expectations:

```python
await manager.async_start()
assert client.async_send_content.await_count == 1
root_id = runtime["garage"].root_event_id
assert root_id == "$panel"
assert client.async_send_event.call_count == len(panel.actions)
```

The root creation path must send one initial bot reaction per configured action key so Element visibly exposes the chips.

- [ ] **Step 2: Implement startup root restore/create rules**

For each enabled panel:
1. resolve room;
2. restore runtime;
3. if stored root exists, validate it with `async_get_event()`;
4. if valid, reuse it;
5. if no stored root (first creation), create one root, increment generation, save, add bot action reactions, best-effort pin;
6. if a previously stored root is now absent/redacted, set `needs_repair=True` and do not auto-create a replacement.

- [ ] **Step 3: Write RED debounce/coalescing tests**

Trigger two configured HA entity changes inside 1.5 seconds, advance test loop, and assert exactly one `m.replace`. Trigger a state change whose render hash is unchanged and assert no edit.

- [ ] **Step 4: Implement entity subscriptions**

Use HA event helpers to subscribe only to the panel's configured entity IDs. Keep unsubscribe callbacks per panel. A dirty panel schedules a single debounce task; later changes inside the window only update desired state.

- [ ] **Step 5: Write Matrix outage test**

Make `async_send_content()` raise `MatrixConnectionError`, then trigger ten HA changes. Assert manager stores the latest desired render and does not create ten retry tasks or touch `PersistentOutbox`. After `async_mark_matrix_available()`/next successful scheduled flush, assert one edit is sent.

- [ ] **Step 6: Implement non-outbox panel retry semantics**

On connection failure, record `last_update_error="connection"`, keep latest desired render, and wait for the listener/account to become connected or for a bounded manager retry. There must be at most one retry task per panel.

- [ ] **Step 7: Implement best-effort pinning**

Call `async_pin_event()` after first root creation and explicit repair. Record `pinned`, `not_pinned`, or error category. Never fail panel startup solely because pin state write is forbidden.

- [ ] **Step 8: Implement explicit repair**

`async_repair(panel_id)` only succeeds for `needs_repair` or missing root. It creates exactly one root, increments generation, clears stale confirmations, registers visible reaction chips, saves runtime and attempts pinning.

- [ ] **Step 9: Implement clean stop**

Cancel debounce/retry tasks, unsubscribe HA listeners, clear pending confirmations, and leave no background tasks.

- [ ] **Step 10: Run tests**

Run: `pytest -q tests/test_control_panel_manager_v060.py tests/test_delivery_behavior.py`

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add custom_components/matrix_extended/control_panel_manager.py \
  tests/test_control_panel_manager_v060.py
git commit -m "feat: manage live Matrix control panels"
```

---

### Task 7: Reaction Routing, Dangerous Confirmation, Redaction Handling and Shared Execution

**Files:**
- Modify: `custom_components/matrix_extended/receiver.py`
- Modify: `custom_components/matrix_extended/control_panel_manager.py`
- Modify: `custom_components/matrix_extended/actions.py`
- Modify: `custom_components/matrix_extended/client.py` (`MatrixAccount` fields)
- Test: `tests/test_receiver_control_panels_v060.py`
- Test: existing receiver/reaction tests

**Interfaces:**
- Panel manager returns a normalized reaction outcome: `handled`, `action_id`, `status`, `error`, `confirmation_prompt_event_id`.
- Receiver tries panel action routing before legacy reaction-action registry execution.
- Legacy reaction actions also execute through `SafeActionExecutor`, never direct `hass.services.async_call()`.

- [ ] **Step 1: Write RED test for low-risk panel reaction**

Use an authorized sender/room and reaction targeting the active root. Assert the manager executes configured `action_id` and receiver marks payload `action_executed=True`.

- [ ] **Step 2: Write RED test for forged events**

Cover wrong root event, unknown emoji, unauthorized sender, unauthorized room and panel user restriction. None may call HA services.

- [ ] **Step 3: Implement panel reaction routing**

`MatrixInboundReceiver.async_handle_reaction()` must keep the existing account-level `_allowed()` check first. Then call panel manager. If the panel manager handled the reaction, do not fall through to the generic reaction registry.

- [ ] **Step 4: Write RED confirmation-flow tests**

Dangerous root reaction should:
1. create a reply such as `⚠️ Confirm: Open garage`;
2. add `✅` and `❌` bot reactions to that prompt;
3. issue 30-second pending confirmation bound to same sender/action/generation;
4. not execute HA yet.

Same sender `✅` executes once. Other sender does nothing. `❌` cancels. Replayed `✅` does nothing.

- [ ] **Step 5: Implement confirmation prompt flow**

Use normal Matrix `m.room.message` reply content and `m.reaction`. Never put the HA service payload into the prompt. Store only identifiers in the pending registry.

- [ ] **Step 6: Route legacy reaction actions through shared executor**

Replace the current direct service call in `receiver.py` with conversion to `SafeActionDefinition` plus `SafeActionExecutor.async_execute()`. Preserve current `EVENT_REACTION` payload compatibility (`action_executed`, `action_service`) while adding normalized failure metadata only when safe.

- [ ] **Step 7: Handle redacted panel roots**

After authorized `m.room.redaction`, pass `room_id` and `redacts` to the panel manager. If it targets an active root, mark `needs_repair=True`, clear confirmations for the panel and cancel future edit attempts until explicit repair.

- [ ] **Step 8: Run tests**

Run:

```bash
pytest -q tests/test_receiver_control_panels_v060.py \
  tests/test_incoming.py tests/test_command_executor_v051.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add custom_components/matrix_extended/receiver.py \
  custom_components/matrix_extended/control_panel_manager.py \
  custom_components/matrix_extended/actions.py \
  custom_components/matrix_extended/client.py tests/
git commit -m "feat: route Matrix reactions through safe panel control"
```

---

### Task 8: Integration Setup/Unload and Listener Ownership

**Files:**
- Modify: `custom_components/matrix_extended/__init__.py`
- Modify: `custom_components/matrix_extended/client.py`
- Modify: `custom_components/matrix_extended/receiver.py`
- Test: `tests/test_setup_control_panels_v060.py`
- Test: `tests/test_client_e2ee.py`

**Interfaces:**
- `MatrixAccount` gains `safe_action_executor` and `panel_manager` runtime fields.
- Panel control remains usable even when generic `incoming_enabled` is false; only panel reaction/redaction callbacks are registered in that case.

- [ ] **Step 1: Write RED setup tests**

Cover:
- no panels: current setup behavior unchanged;
- panels + incoming enabled: one shared receiver handles general events and delegates control;
- panels + incoming disabled: Matrix sync listener still starts for control, but generic Matrix message/media HA events are not registered/fired;
- unload stops panel manager before closing Matrix client.

- [ ] **Step 2: Add panel config/runtime Store setup**

In `async_setup_entry()`, normalize `CONF_CONTROL_PANELS`, construct `Store(hass, 1, f"{DOMAIN}.control_panels_{entry.entry_id}", private=True)`, create `SafeActionExecutor`, then create `ControlPanelManager`.

- [ ] **Step 3: Define listener registration modes**

Refactor `MatrixInboundReceiver.register()` to accept a mode with exact semantics:

```python
receiver.register(control_only=False)  # all current callbacks
receiver.register(control_only=True)   # only reactions/redactions needed by panels
```

When `control_only=True`, reaction/redaction handlers may control panels but must not execute legacy arbitrary reaction actions or fire the general incoming HA events that the user explicitly disabled.

- [ ] **Step 4: Start panel manager and Matrix listener**

Order:
1. account runtime constructed and stored in `hass.data`;
2. panel manager `async_start()`;
3. register receiver in full or control-only mode;
4. call `client.async_start_listener()` when generic incoming or any panel is enabled.

- [ ] **Step 5: Unload without task leaks**

Call `await panel_manager.async_stop()` before canceling outbox/client tasks. Clear pending confirmations on every reload/unload.

- [ ] **Step 6: Run tests**

Run:

```bash
pytest -q tests/test_setup_control_panels_v060.py \
  tests/test_client_e2ee.py tests/test_client_timeout_policy.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/matrix_extended/__init__.py \
  custom_components/matrix_extended/client.py \
  custom_components/matrix_extended/receiver.py \
  tests/test_setup_control_panels_v060.py
git commit -m "feat: wire Matrix control panels into HA lifecycle"
```

---

### Task 9: Graphical Options Flow CRUD and YAML Import/Export

**Files:**
- Modify: `custom_components/matrix_extended/config_flow.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Test: `tests/test_config_flow_control_panels_v060.py`
- Test: `tests/test_config_flow_ui_schema.py`
- Test: `tests/test_documentation_localization.py`

**Interfaces:**
- Adds menu `control_panels` to Options Flow.
- Adds steps: `panel_add`, `panel_edit`, `panel_edit_details`, `panel_delete`, `panel_import`, `panel_export_select`, `panel_export`.
- Uses HA entity selectors for entities and current Matrix room metadata for room selection.

- [ ] **Step 1: Write RED menu/CRUD schema tests**

Assert `async_step_init()` includes `control_panels`. Add flow tests that create one panel and persist it under `CONF_CONTROL_PANELS` without overwriting unrelated options.

- [ ] **Step 2: Implement panel menu and selection state**

Mirror the existing route-management pattern, but keep panel editing in multiple focused forms rather than one giant schema.

Recommended flow:

```text
Control panels
  Add panel
  Edit panel
  Delete panel
  Import YAML
  Export YAML
```

- [ ] **Step 3: Implement panel add/edit forms**

Use:
- room: `SelectSelector` built from `account.rooms`/room labels;
- entities: `EntitySelector(multiple=True)`;
- allowed users: multiline/multiple text selector;
- debounce: number selector `0.25..10.0`;
- action details: stable ID, label, reaction, service string, target object, data object, confirmation boolean.

Because HA's form schema is static per step, collect actions with repeated `panel_action_add/edit/delete` substeps rather than trying to encode arbitrary nested action arrays in one field.

- [ ] **Step 4: Enforce account security in UI validation**

Before `_finish()`, call the same pure `normalize_control_panels()` validator used at runtime. Show specific errors for room outside allowlist, user outside allowlist, duplicate reaction/action and duplicate room.

- [ ] **Step 5: Implement YAML import/export**

Import: multiline text selector -> `load_panel_yaml()` -> validation -> replace panel with same ID or add new panel after explicit confirmation when replacing.

Export: choose panel -> multiline text field prefilled with `dump_panel_yaml(panel)`. Submitting export performs no config mutation; it returns to panel menu.

- [ ] **Step 6: Add EN/RU strings**

Every new menu item, field, error and description must exist in both `strings.json` and `translations/ru.json`. Keep Russian wording practical and explicit about dangerous-action confirmation and allowlist narrowing.

- [ ] **Step 7: Run tests**

Run:

```bash
pytest -q tests/test_config_flow_control_panels_v060.py \
  tests/test_config_flow_ui_schema.py \
  tests/test_documentation_localization.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add custom_components/matrix_extended/config_flow.py \
  custom_components/matrix_extended/strings.json \
  custom_components/matrix_extended/translations/ru.json tests/
git commit -m "feat: configure Matrix control panels in HA UI"
```

---

### Task 10: Panel Diagnostics Sensor and Runtime Visibility

**Files:**
- Modify: `custom_components/matrix_extended/sensor.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Test: `tests/test_control_panel_diagnostics_v060.py`
- Test: `tests/test_diagnostics_v051.py`

**Interfaces:**
- Adds one disabled-by-default diagnostic sensor `control_panels` per Matrix account.
- Native value: number of active panels.
- Attributes: bounded list of per-panel diagnostic snapshots.

- [ ] **Step 1: Write RED diagnostics tests**

Expected snapshot keys per panel:

```python
{
    "panel_id", "room_id", "root_event_id", "state", "pin_status",
    "watched_entities", "actions", "last_update_at", "last_update_error",
    "pending_confirmations",
}
```

Ensure no HA service data, access tokens or secrets are exposed.

- [ ] **Step 2: Implement manager listener + sensor**

`ControlPanelManager.add_listener()` notifies on root/pin/repair/update/confirmation-count changes. `MatrixControlPanelsSensor` subscribes and publishes a bounded snapshot. Use `EntityCategory.DIAGNOSTIC` and `_attr_entity_registry_enabled_default = False`.

- [ ] **Step 3: Add translations**

Add `entity.sensor.control_panels.name` in EN/RU.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest -q tests/test_control_panel_diagnostics_v060.py tests/test_diagnostics_v051.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/sensor.py \
  custom_components/matrix_extended/strings.json \
  custom_components/matrix_extended/translations/ru.json tests/
git commit -m "feat: expose Matrix control panel diagnostics"
```

---

### Task 11: User Documentation for Native Matrix Control

**Files:**
- Create: `docs/CONTROL_PANELS.md`
- Create: `docs/CONTROL_PANELS.ru.md`
- Modify: `README.md`
- Modify: `README.ru.md`
- Modify: `docs/EXAMPLES.md`
- Modify: `docs/EXAMPLES.ru.md`
- Test: `tests/test_documentation_localization.py`

**Interfaces:**
- Documents actual `0.6.0b1` behavior only; Widget remains explicitly future/beta roadmap.

- [ ] **Step 1: Add documentation localization assertions**

Require EN/RU control-panel docs and matching section anchors/feature terms.

- [ ] **Step 2: Write control panel guide**

Include:
- prerequisites and allowlists;
- GUI creation flow;
- one-panel-per-room rule;
- normal vs dangerous reactions;
- 30-second same-sender confirmation;
- pin power-level behavior;
- `needs_repair` and explicit repair;
- YAML import/export example;
- state/debounce semantics;
- security warning that Matrix cannot submit arbitrary HA services.

- [ ] **Step 3: Add practical examples**

Add garage, alarm, light/climate examples. Include a dangerous garage open action and low-risk light toggle.

- [ ] **Step 4: Update README feature list**

Mark Native Matrix Control as `0.6.0b1` and Widget as planned `0.6.0b2`; do not describe Widget as already shipped.

- [ ] **Step 5: Run docs tests**

Run: `pytest -q tests/test_documentation_localization.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/CONTROL_PANELS.md docs/CONTROL_PANELS.ru.md \
  README.md README.ru.md docs/EXAMPLES.md docs/EXAMPLES.ru.md \
  tests/test_documentation_localization.py
git commit -m "docs: document native Matrix control panels"
```

---

### Task 12: Real HA/Synapse/Element Regression for Control Panels

**Files:**
- Modify: `ci/scripts/prepare-ha.sh`
- Create: `ci/scripts/matrix-control-e2e.py`
- Modify: `.github/workflows/test.yml`
- Test: `tests/e2e/test_ha_e2e_helpers.py` or create `tests/e2e/test_matrix_control_helpers.py`

**Interfaces:**
- Real test uses current disposable room and users from `.ci/matrix-env.json`.
- Uses deterministic HA helpers from `prepare-ha.sh`.
- Must prove both low-risk and dangerous action flows in an encrypted room.

- [ ] **Step 1: Extend HA fixture**

Add deterministic entities:

```yaml
input_boolean:
  matrix_control_light:
    name: Matrix control light
    initial: false
  matrix_control_dangerous:
    name: Matrix control dangerous target
    initial: false
```

Use services `input_boolean.turn_on` / `turn_off` so real state transitions are observable.

- [ ] **Step 2: Add E2E helper unit tests**

Test pure functions used to locate/decrypt panel root/edit events and build reactions. Keep network calls outside unit tests.

- [ ] **Step 3: Implement `matrix-control-e2e.py configure`**

Use HA config-entry Options Flow HTTP API to create a panel in the existing encrypted room with:
- light state entity + low-risk `💡` action;
- dangerous target + `🔓` action requiring confirmation;
- allowed user equal to the disposable Element user.

Wait for reload and record root event ID.

- [ ] **Step 4: Implement live state/edit assertion**

Change `input_boolean.matrix_control_light` through HA API, sync/decrypt as the Matrix user, and assert Element/Matrix receives an edit related to the same root event rather than a new root.

- [ ] **Step 5: Implement low-risk control assertion**

React `💡` to the root as the allowed Matrix user. Wait for HA entity state to change, then assert one panel edit reflects real state.

- [ ] **Step 6: Implement dangerous confirmation assertion**

React `🔓` to root. Assert HA target remains off. Discover confirmation reply, react `✅` as same user, assert HA target becomes on. Add a negative attempt with a second Matrix user or unauthorized sender if bootstrap fixture already has one; otherwise create one in bootstrap for this test.

- [ ] **Step 7: Test Synapse outage coalescing**

Before stopping Synapse, record panel state. While Synapse is down, make several HA state flips. After Synapse restart, assert only the final desired state is reflected by the first successful panel update; do not require every intermediate transition.

- [ ] **Step 8: Test HA restart root stability**

After HA restart, assert stored root event ID is unchanged and no duplicate control root is created.

- [ ] **Step 9: Test redaction/repair behavior**

Redact root as permitted test user/admin, verify diagnostics becomes `needs_repair`, and verify no automatic root storm. Invoke the explicit repair path through the configured UI/service mechanism implemented for b1 and assert exactly one new root.

- [ ] **Step 10: Add workflow gate**

Insert a real-stack step after safe commands/Voice Assist and before outage/restart steps:

```yaml
- name: Verify encrypted Native Matrix Control panels
  run: python ci/scripts/matrix-control-e2e.py verify
```

Preserve existing real-stack timeout unless measured runtime requires a bounded increase.

- [ ] **Step 11: Run local fast tests**

Run:

```bash
pytest -q tests/e2e/test_matrix_control_helpers.py
python -m compileall -q custom_components/matrix_extended ci/scripts
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add ci/scripts/prepare-ha.sh ci/scripts/matrix-control-e2e.py \
  .github/workflows/test.yml tests/e2e/
git commit -m "test: cover Matrix control panels on real HA stack"
```

---

### Task 13: Beta Release Semantics, Version, Changelog and Final Verification

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `custom_components/matrix_extended/manifest.json`
- Modify: `CHANGELOG.md`
- Modify: `CHANGELOG.ru.md`
- Modify: release-related tests if present

**Interfaces:**
- Version becomes exactly `0.6.0b1` only when implementation is release-ready.
- Release workflow detects pre-release versions and uses GitHub `--prerelease`, never `--latest` for beta.

- [ ] **Step 1: Write release-workflow contract test if repository has workflow tests; otherwise add `tests/test_release_workflow.py`**

Parse `.github/workflows/release.yml` as text and assert beta-aware logic exists:

```python
assert "--prerelease" in workflow
assert "--latest" in workflow
assert "0.6.0b1" not in workflow  # logic must be generic, not hard-coded
```

- [ ] **Step 2: Make release mode generic**

In `release.yml`, derive pre-release status from Python packaging-version semantics or a conservative regex matching `a`, `b`, `rc` segments. Emit `prerelease=true/false` as a step output.

For pre-release:

```bash
gh release create "$tag" ... --prerelease ...
```

For stable:

```bash
gh release create "$tag" ... --latest ...
```

Do not mark beta as latest.

- [ ] **Step 3: Run the entire fast gate before version bump**

Run:

```bash
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

Expected: all PASS.

- [ ] **Step 4: Bump manifest to `0.6.0b1` and add bilingual changelog**

`CHANGELOG.md` and `CHANGELOG.ru.md` must include:
- Native Matrix Control overview;
- existing-room limitation;
- reaction controls and dangerous confirmations;
- persistence/recovery/pin behavior;
- GUI + YAML import/export;
- diagnostics;
- real-stack test status;
- note that Widget is not included yet and is planned for later beta.

- [ ] **Step 5: Run full local regression again**

Run:

```bash
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
python ci/scripts/build-release.py
```

Expected: PASS and a verified `dist/matrix_extended-ha-install-v0.6.0b1.zip`.

- [ ] **Step 6: Push implementation branch and open PR to `main`**

PR body must list the design spec, test coverage, real-stack requirements, and explicitly state that release publication is blocked on all CI gates.

- [ ] **Step 7: Require CI proof before merge**

Do not merge until all are green for the exact PR head:
- Fast regression gate;
- Clean manifest runtime Python 3.14 + E2EE;
- Real HA 2026.9.2 + Synapse 1.160.0 + Element 1.12.26;
- Verified install ZIP;
- Hassfest;
- HACS validation.

- [ ] **Step 8: Merge only after exact-head green, then verify main CI**

After merge, confirm the same gates pass for the exact merge commit on `main`.

- [ ] **Step 9: Verify generated GitHub Pre-release**

Check:
- tag `v0.6.0b1`;
- release marked Pre-release;
- exact tested main commit target;
- bilingual notes;
- install ZIP;
- `.sha256` asset;
- release does not become `Latest`.

- [ ] **Step 10: Commit release-prep changes before PR review**

```bash
git add .github/workflows/release.yml \
  custom_components/matrix_extended/manifest.json \
  CHANGELOG.md CHANGELOG.ru.md tests/
git commit -m "release: prepare Matrix Extended 0.6.0b1"
```

---

## Plan Self-Review Checklist

Before implementation handoff, verify:

1. Every spec requirement maps to at least one task above.
2. No task creates a second authorization/execution engine.
3. General incoming events can remain disabled while panel control still has a narrow reaction/redaction listener path.
4. Pending confirmations are memory-only and are cleared on reload/restart.
5. Lost/redacted roots never cause automatic message storms.
6. Pinning failure is non-fatal.
7. HA state, not service-call success, drives visible panel state.
8. Panel outage handling never feeds every state edit into the persistent normal-message outbox.
9. Widget support is only an interface boundary in b1; no Widget implementation is included.
10. Beta publication is Pre-release and not Latest.
