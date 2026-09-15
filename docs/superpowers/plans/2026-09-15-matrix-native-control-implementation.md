# Matrix Native Control 0.6.0b1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `0.6.0b1` Native Matrix Control: one maintained control panel per existing Matrix room, live HA state rendering, reaction-driven safe actions, two-step confirmation for dangerous actions, persistence/recovery, GUI configuration, diagnostics, and real-stack release validation.

**Architecture:** Home Assistant remains the source of truth. Panel configuration lives in `config_entry.options`; runtime root-event metadata lives in `Store`; pending confirmations are memory-only and are always discarded on reload/restart. Matrix reactions, existing safe commands, and future Widget actions normalize to one safe action execution core. Panel state changes are event-driven, debounced, and emitted as `m.replace` edits of a stable root event.

**Tech Stack:** Home Assistant 2026.9.x custom integration APIs, Python 3.13/3.14, `matrix-nio[e2e]==0.26.0`, Synapse 1.160.0, Element Web 1.12.26, pytest 9, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-15-matrix-native-control-design.md`

## Global Constraints

- `0.6.0b1` uses existing Matrix rooms only; no automatic Space/room creation.
- Account-level `allowed_users` and resolved `allowed_rooms` are the outer fail-closed boundary; panel rules may only narrow access.
- Persist panel room IDs, not aliases. Resolve account aliases before validating panel room membership.
- Matrix events never provide arbitrary executable `domain.service` payloads; they reference preconfigured action IDs.
- Home Assistant state is authoritative; do not optimistically mutate panel state after a service call.
- One panel per Matrix room for `0.6.0b1`.
- Panel updates use HA state subscriptions, not polling.
- Default panel debounce is 1.5 seconds.
- Dangerous-action confirmation expires after 30 seconds and only the same Matrix sender may confirm.
- Pending confirmations are never persisted and are dropped on reload/restart.
- Root loss/redaction moves a panel to `needs_repair`; do not create roots in a retry loop.
- Pinning is best-effort. Missing Matrix power level is diagnostic-only and must not disable control.
- A valid existing root may be re-pinned once during startup recovery; never fight an unpin continuously during normal sync.
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
- `custom_components/matrix_extended/control_panel_manager.py` — panel lifecycle, HA subscriptions, debounce, Matrix writes, action routing, pin/repair logic and diagnostics snapshots.

Existing modules changed:

- `actions.py`, `commands.py`, `command_executor.py` — reuse one safe-action core.
- `client.py`, `content.py` — room-event/state helpers, pins, panel metadata-preserving edits.
- `receiver.py`, `__init__.py` — inbound control routing and lifecycle wiring.
- `config_flow.py`, `const.py`, `strings.json`, `translations/ru.json` — panel GUI CRUD, repair, YAML import/export.
- `sensor.py` — panel diagnostics.
- `README*`, `docs/*` — user docs.
- `ci/scripts/*`, `.github/workflows/test.yml`, `.github/workflows/release.yml` — real-stack test and beta release semantics.

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
- Test: `tests/test_camera_command_v051.py`

**Interfaces:**
- `ServiceActionHandler(service: str, target: dict[str, Any], data: dict[str, Any])`.
- `CameraSnapshotActionHandler(entity_id: str, caption: str)`.
- `SafeActionDefinition(id: str, handler: ServiceActionHandler | CameraSnapshotActionHandler, confirmation_required: bool = False)`.
- `SafeActionExecutionContext(account: Any | None = None, room_id: str | None = None, thread_id: str | None = None, prepared_room: Any | None = None)`.
- `SafeActionExecutionResult(action_id: str, status: str, handler_type: str, error: str | None)`.
- `SafeActionExecutor.async_execute(action: SafeActionDefinition, *, context: SafeActionExecutionContext | None = None) -> SafeActionExecutionResult`.

- [ ] **Step 1: Write pure-model RED tests**

```python
from custom_components.matrix_extended.safe_actions import (
    SafeActionDefinition,
    ServiceActionHandler,
    parse_service_handler,
)


def test_service_handler_rejects_invalid_service():
    with pytest.raises(ValueError, match="domain.service"):
        parse_service_handler({"service": "broken"})


def test_safe_action_keeps_preconfigured_payload():
    action = SafeActionDefinition(
        id="garage.open",
        handler=ServiceActionHandler(
            service="cover.open_cover",
            target={"entity_id": "cover.garage"},
            data={},
        ),
        confirmation_required=True,
    )
    assert action.handler.service == "cover.open_cover"
    assert action.confirmation_required is True
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_safe_actions_v060.py`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement pure action dataclasses and validators**

Reuse current validation semantics from `commands.py`. Add stable JSON-safe dump helpers. Matrix sender/room authorization stays outside this module.

- [ ] **Step 4: Write executor RED tests**

```python
result = await SafeActionExecutor(hass).async_execute(action)
assert result.status == "success"
hass.services.async_call.assert_awaited_once_with(
    "cover", "open_cover", {}, blocking=True,
    target={"entity_id": "cover.garage"},
)
```

Also assert an exception containing `token=abc123` produces `token=<redacted>`.

- [ ] **Step 5: Implement executor**

Move reusable `_safe_error()` and service execution from `command_executor.py`. For `CameraSnapshotActionHandler`, require `SafeActionExecutionContext` with Matrix account/room and reuse the current `MediaResolver` + upload/send path. If required camera context is missing, return a bounded failed result rather than executing partially.

- [ ] **Step 6: Adapt commands and reaction actions**

Keep existing persisted command/reaction Store schemas compatible. Add adapters that convert stored handlers/actions to `SafeActionDefinition` at execution time.

- [ ] **Step 7: Make `CommandExecutor` delegate**

Keep progress-message creation/editing in `command_executor.py`; replace direct service/camera execution with `SafeActionExecutor.async_execute()` and pass `SafeActionExecutionContext(account=..., room_id=..., thread_id=..., prepared_room=...)`.

- [ ] **Step 8: Run focused regression**

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
- Modify: `requirements-test.txt`
- Test: `tests/test_control_panels_v060.py`

**Interfaces:**
- `PanelEntity(entity_id: str, label: str)`.
- `PanelAction(id: str, reaction: str, label: str, action: SafeActionDefinition)`.
- `ControlPanelDefinition(panel_id, room_id, title, enabled, entities, actions, allowed_users, debounce)`.
- `normalize_control_panels(raw, *, account_allowed_users: set[str], account_allowed_room_ids: set[str]) -> dict[str, ControlPanelDefinition]`.
- `dump_panel_yaml(panel) -> str`.
- `load_panel_yaml(text, *, account_allowed_users: set[str], account_allowed_room_ids: set[str]) -> ControlPanelDefinition`.

- [ ] **Step 1: Write validation RED tests**

Cover duplicate room, duplicate action ID, duplicate reaction key, duplicate entity ID, panel user outside account allowlist, room ID outside resolved account room allowlist and default debounce 1.5 seconds.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/test_control_panels_v060.py`

Expected: FAIL because the module is missing.

- [ ] **Step 3: Implement panel dataclasses and normalization**

Persist only room IDs. Reject room aliases in panel definitions so runtime authorization is deterministic. Accept debounce only in `0.25..10.0` seconds.

- [ ] **Step 4: Add PyYAML test dependency and YAML round-trip tests**

Add `PyYAML==6.0.3` to `requirements-test.txt` for the fast suite. Home Assistant already supplies PyYAML at runtime.

```python
yaml_text = dump_panel_yaml(panel)
loaded = load_panel_yaml(
    yaml_text,
    account_allowed_users={"@owner:matrix.test"},
    account_allowed_room_ids={"!room:matrix.test"},
)
assert loaded == panel
```

Reject multi-document YAML and non-mapping roots. Use `yaml.safe_load`/`safe_dump` only.

- [ ] **Step 5: Add constants**

Add `CONF_CONTROL_PANELS = "control_panels"` and stable panel/action field constants used by Options Flow.

- [ ] **Step 6: Run tests**

Run: `pytest -q tests/test_control_panels_v060.py tests/test_config_flow_ui_schema.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/matrix_extended/control_panels.py \
  custom_components/matrix_extended/const.py requirements-test.txt \
  tests/test_control_panels_v060.py
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
- `MatrixClient.async_get_event(room: str, event_id: str) -> Mapping[str, Any] | None`.
- `MatrixClient.async_get_state_event(room: str, event_type: str, state_key: str = "") -> Mapping[str, Any] | None`.
- `MatrixClient.async_put_state_event(room: str, event_type: str, content: dict[str, Any], state_key: str = "") -> str | None`.
- `MatrixClient.async_pin_event(room: str, event_id: str) -> bool` merges `m.room.pinned_events` and preserves unrelated pins.
- Panel-aware text/edit builders keep `io.psix.matrix_extended.panel` in root content and `m.new_content`.

- [ ] **Step 1: Write pin-merge RED tests**

```python
existing = {"pinned": ["$foreign"]}
await client.async_pin_event("!room:test", "$panel")
assert fake_nio.room_put_state.await_args.kwargs["content"] == {
    "pinned": ["$foreign", "$panel"]
}
```

Also assert an already-pinned event performs no write.

- [ ] **Step 2: Implement room event/state wrappers**

Wrap matrix-nio `room_get_event`, `room_get_state_event` and `room_put_state`. Convert Matrix error responses to existing transport/send error categories. Treat a true missing/redacted root as unavailable; do not silently convert authorization/transport errors to `None`.

- [ ] **Step 3: Write panel metadata RED tests**

Assert root and replacement `m.new_content` contain:

```python
"io.psix.matrix_extended.panel": {"schema": 1, "panel_id": "garage"}
```

- [ ] **Step 4: Extend content builders safely**

Add optional `extra_content: Mapping[str, Any] | None` to `build_text_content()` and `build_edit_content()`. Forbid overriding `msgtype`, `body`, `m.relates_to` or `m.new_content`.

- [ ] **Step 5: Run tests**

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
- `RenderedPanel(body: str, formatted_body: str, digest: str)`.
- `render_control_panel(panel: ControlPanelDefinition, states: Mapping[str, Any]) -> RenderedPanel`.

- [ ] **Step 1: Write RED domain-state tests**

Cover light on/off, cover closed/opening, alarm armed/disarmed, climate state/temperature, sensor units and unknown-domain fallback.

- [ ] **Step 2: Write escaping/order tests**

Assert entity/action order is stable and strings such as `<Garage>` are escaped only in HTML.

- [ ] **Step 3: Implement renderer**

Use small domain helpers. Do not execute templates/Jinja. Digest stable UTF-8 `body + formatted_body` with SHA256. Do not put current wall-clock time into the digest or body; unchanged HA state must remain unchanged output.

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
- `PanelRuntime(panel_id, room_id, root_event_id, render_hash, generation, pin_status, pin_error, needs_repair, last_update_at, last_update_error)`.
- `ControlPanelRuntimeStore.restore()/dump()/async_save()`.
- `PendingConfirmationRegistry.issue(...)`, `.consume(...)`, `.cancel(...)`, `.clear_panel(...)`, `.count`, `.clear()`.
- Confirmation key is prompt `event_id`.

- [ ] **Step 1: Write persistence RED tests**

Assert JSON-safe round trip preserves root/generation/pin/repair state and never contains pending confirmations.

- [ ] **Step 2: Write confirmation RED tests**

Test same sender success, other sender non-consumption, 30-second expiry, stale generation, cancel, replay rejection and global clear on reload.

- [ ] **Step 3: Implement runtime models/store adapter**

Use monotonically increasing integer `generation` per new root.

- [ ] **Step 4: Implement memory-only confirmation registry**

Store prompt event ID, panel ID, action ID, sender, generation and expiry only. Valid `consume()` removes atomically; wrong sender does not consume.

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

### Task 6: Control Panel Manager Lifecycle, Debounce, Roots, Pins and Repair

**Files:**
- Create: `custom_components/matrix_extended/control_panel_manager.py`
- Test: `tests/test_control_panel_manager_v060.py`

**Interfaces:**
- `ControlPanelManager.async_start()` / `async_stop()`.
- `async_handle_reaction(room_id, root_or_prompt_event_id, reaction, sender)`.
- `async_handle_redaction(room_id, redacted_event_id)`.
- `async_repair(panel_id)`.
- `diagnostics_snapshot()` and `add_listener()`.

- [ ] **Step 1: Write RED first-start/root-reuse tests**

First start creates one root and one bot reaction per configured action. Restart with a valid stored root creates no root and preserves event ID.

- [ ] **Step 2: Implement startup root rules**

For each enabled panel: resolve/confirm room ID; restore runtime; validate stored root; reuse valid root; first-ever panel creates one root; previously known missing/redacted root becomes `needs_repair` without auto-replacement.

- [ ] **Step 3: Write debounce RED tests**

Two HA entity changes inside 1.5 seconds -> one `m.replace`. Render hash unchanged -> zero edits.

- [ ] **Step 4: Implement HA state subscriptions**

Subscribe only configured entity IDs. Keep one debounce task per panel and unsubscribe callbacks for stop/reload.

- [ ] **Step 5: Write outage-coalescing RED test**

Make Matrix edit fail with `MatrixConnectionError`, trigger ten HA changes, and assert no general `PersistentOutbox` entries and no ten retry tasks. Latest desired render is kept.

- [ ] **Step 6: Implement bounded panel retry**

At most one retry/flush task per panel. When Matrix is available again, send only latest desired render.

- [ ] **Step 7: Implement pin behavior**

On first creation, valid-root startup recovery and explicit repair, read/merge pins and attempt pin once. Record permission failure as non-fatal diagnostics. Never re-pin on every sync/state change.

- [ ] **Step 8: Implement explicit repair**

`async_repair(panel_id)` creates exactly one new root only when root is missing/repair-needed, increments generation, clears panel confirmations, adds action reaction chips, saves runtime and attempts pinning.

- [ ] **Step 9: Implement clean stop**

Cancel debounce/retry tasks, unsubscribe HA listeners and clear pending confirmations.

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

### Task 7: Reaction Routing, Dangerous Confirmation, Redaction and Shared Execution

**Files:**
- Modify: `custom_components/matrix_extended/receiver.py`
- Modify: `custom_components/matrix_extended/control_panel_manager.py`
- Modify: `custom_components/matrix_extended/actions.py`
- Modify: `custom_components/matrix_extended/client.py`
- Test: `tests/test_receiver_control_panels_v060.py`

**Interfaces:**
- Panel manager reaction outcome contains `handled`, `action_id`, `status`, `error`, `confirmation_prompt_event_id`.
- Receiver checks panel routing before legacy reaction registry.
- Legacy reaction actions execute through `SafeActionExecutor`, not direct HA service calls.

- [ ] **Step 1: Write RED low-risk panel reaction test**

Authorized sender + active root + known emoji executes configured action exactly once.

- [ ] **Step 2: Write forged-event RED tests**

Wrong root, unknown emoji, unauthorized sender/room and panel user restriction must not call HA.

- [ ] **Step 3: Implement panel-first reaction routing**

Keep account `_allowed()` first. If panel manager handles the reaction, do not fall through to legacy reaction registry.

- [ ] **Step 4: Write dangerous confirmation RED tests**

Dangerous root reaction sends reply `⚠️ Confirm: ...`, adds bot `✅`/`❌` reactions and does not execute HA. Same sender `✅` executes once; other sender does nothing; `❌` cancels; replay does nothing.

- [ ] **Step 5: Implement confirmation prompt**

Prompt content carries only labels/IDs; never HA service payload. Registry binds prompt to panel/action/sender/generation for 30 seconds.

- [ ] **Step 6: Migrate legacy reaction execution**

Convert consumed legacy reaction action to `SafeActionDefinition`, execute with shared executor, preserve current `EVENT_REACTION` compatibility fields.

- [ ] **Step 7: Handle root redaction**

Authorized redaction targeting active root sets `needs_repair=True`, clears panel confirmations and suppresses future edits until explicit repair.

- [ ] **Step 8: Run tests**

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

**Interfaces:**
- `MatrixAccount` gains `safe_action_executor` and `panel_manager`.
- Panel control works even when generic `incoming_enabled` is false, using only narrow reaction/redaction callbacks.

- [ ] **Step 1: Write RED lifecycle tests**

Cover no-panels current behavior, panels + incoming enabled, panels + incoming disabled, and unload ordering.

- [ ] **Step 2: Resolve account allowed rooms before panel normalization**

Reuse existing `allowed_rooms = {await client.async_resolve_room(...)}`. Only after this set exists, call `normalize_control_panels(..., account_allowed_room_ids=allowed_rooms)`. This makes alias-based account config compatible with room-ID-based panel config.

- [ ] **Step 3: Construct panel runtime**

Create private HA Store `f"{DOMAIN}.control_panels_{entry.entry_id}"`, shared executor and manager; attach to `MatrixAccount`.

- [ ] **Step 4: Add receiver registration modes**

```python
receiver.register(control_only=False)  # all current callbacks
receiver.register(control_only=True)   # panel reactions/redactions only
```

In control-only mode do not fire general incoming HA events and do not execute legacy generic reaction actions.

- [ ] **Step 5: Start listener under correct conditions**

Start Matrix sync listener when generic incoming is enabled **or** at least one panel is enabled. Start manager before callback registration so reactions can be routed immediately.

- [ ] **Step 6: Unload cleanly**

`await panel_manager.async_stop()` before client close; pending confirmations are cleared every reload/unload.

- [ ] **Step 7: Run tests**

```bash
pytest -q tests/test_setup_control_panels_v060.py \
  tests/test_client_e2ee.py tests/test_client_timeout_policy.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add custom_components/matrix_extended/__init__.py \
  custom_components/matrix_extended/client.py \
  custom_components/matrix_extended/receiver.py \
  tests/test_setup_control_panels_v060.py
git commit -m "feat: wire Matrix control panels into HA lifecycle"
```

---

### Task 9: Graphical Options Flow CRUD, Repair and YAML Import/Export

**Files:**
- Modify: `custom_components/matrix_extended/config_flow.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Test: `tests/test_config_flow_control_panels_v060.py`
- Test: `tests/test_config_flow_ui_schema.py`
- Test: `tests/test_documentation_localization.py`

**Interfaces:**
- Add `control_panels` menu.
- Add steps `panel_add`, `panel_edit`, `panel_edit_details`, `panel_action_add`, `panel_action_edit`, `panel_action_delete`, `panel_delete`, `panel_repair`, `panel_import`, `panel_export_select`, `panel_export`.

- [ ] **Step 1: Write RED menu/CRUD tests**

Assert panel menu exists and adding a panel updates only `CONF_CONTROL_PANELS` while preserving unrelated options.

- [ ] **Step 2: Implement panel menu and temporary edit state**

Use the existing route-management style. Menu entries: Add, Edit, Delete, Repair, Import YAML, Export YAML.

- [ ] **Step 3: Implement panel forms**

Room selector uses currently joined Matrix rooms but stores `room_id`. Entity selector is multiple HA entities. Debounce number selector is `0.25..10.0`. Manage arbitrary action count through action add/edit/delete substeps rather than nested opaque JSON.

- [ ] **Step 4: Validate against resolved runtime account policy**

Use loaded account `incoming_policy.allowed_rooms` for resolved room IDs and the account configured allowed users. Call the same pure panel normalizer before `_finish()`.

- [ ] **Step 5: Implement explicit Repair panel UI**

Choose a configured panel, call `await account.panel_manager.async_repair(panel_id)`, show success or `not_needs_repair`/Matrix error, then return to panel menu. This is the user-facing explicit repair path required by the spec; it does not mutate panel configuration.

- [ ] **Step 6: Implement YAML import/export**

Import multiline YAML -> safe parse -> validator -> add or replace by `panel_id`; require explicit replace confirmation. Export choose panel -> multiline prefilled YAML text; submit returns to menu without changing config.

- [ ] **Step 7: Add EN/RU strings**

Add every menu item, field, description and error in both locales, including repair and dangerous confirmation wording.

- [ ] **Step 8: Run tests**

```bash
pytest -q tests/test_config_flow_control_panels_v060.py \
  tests/test_config_flow_ui_schema.py \
  tests/test_documentation_localization.py
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add custom_components/matrix_extended/config_flow.py \
  custom_components/matrix_extended/strings.json \
  custom_components/matrix_extended/translations/ru.json tests/
git commit -m "feat: configure Matrix control panels in HA UI"
```

---

### Task 10: Panel Diagnostics Sensor

**Files:**
- Modify: `custom_components/matrix_extended/sensor.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Test: `tests/test_control_panel_diagnostics_v060.py`

**Interfaces:**
- Disabled-by-default `control_panels` diagnostic sensor per account.
- Native value: number of active panels.
- Attributes: bounded per-panel snapshots.

- [ ] **Step 1: Write RED diagnostics test**

Require keys `panel_id`, `room_id`, `root_event_id`, `state`, `pin_status`, `watched_entities`, `actions`, `last_update_at`, `last_update_error`, `pending_confirmations`. Assert no service data/tokens/secrets.

- [ ] **Step 2: Implement manager listeners and sensor**

Notify listeners on root/pin/repair/update/confirmation count changes. Sensor subscribes via `async_on_remove`.

- [ ] **Step 3: Add EN/RU entity translation**

Add `entity.sensor.control_panels.name`.

- [ ] **Step 4: Run tests**

Run: `pytest -q tests/test_control_panel_diagnostics_v060.py tests/test_diagnostics_v051.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/sensor.py \
  custom_components/matrix_extended/strings.json \
  custom_components/matrix_extended/translations/ru.json tests/
git commit -m "feat: expose Matrix control panel diagnostics"
```

---

### Task 11: User Documentation

**Files:**
- Create: `docs/CONTROL_PANELS.md`
- Create: `docs/CONTROL_PANELS.ru.md`
- Modify: `README.md`
- Modify: `README.ru.md`
- Modify: `docs/EXAMPLES.md`
- Modify: `docs/EXAMPLES.ru.md`
- Test: `tests/test_documentation_localization.py`

- [ ] **Step 1: Extend localization tests**

Require EN/RU control-panel docs and matching high-level sections.

- [ ] **Step 2: Document actual b1 behavior**

Cover prerequisites/allowlists, GUI creation, one-panel-per-room, normal/dangerous reactions, 30-second same-sender confirmation, pin power level behavior, `needs_repair` + Repair UI, YAML import/export, debounce/outage behavior and security boundary.

- [ ] **Step 3: Add practical examples**

Garage, alarm and light/climate examples with at least one dangerous and one low-risk action.

- [ ] **Step 4: Update README roadmap**

Native Control = `0.6.0b1`; Matrix Widget remains planned for later beta, not shipped.

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

### Task 12: Real HA/Synapse/Element Regression

**Files:**
- Modify: `ci/scripts/prepare-ha.sh`
- Create: `ci/scripts/matrix-control-e2e.py`
- Modify: `.github/workflows/test.yml`
- Test: `tests/e2e/test_matrix_control_helpers.py`

- [ ] **Step 1: Extend deterministic HA fixture**

```yaml
input_boolean:
  matrix_control_light:
    name: Matrix control light
    initial: false
  matrix_control_dangerous:
    name: Matrix control dangerous target
    initial: false
```

- [ ] **Step 2: Write helper unit tests**

Test functions that identify/decrypt panel root, edit relation and confirmation reply; keep network I/O outside unit tests.

- [ ] **Step 3: Implement real panel configuration through Options Flow HTTP API**

Create panel in the existing encrypted room with a low-risk `💡 -> input_boolean.toggle matrix_control_light` and dangerous `🔓 -> input_boolean.turn_on matrix_control_dangerous` action.

- [ ] **Step 4: Verify live HA state -> same-root edit**

Change light via HA API, sync/decrypt Matrix events and assert an `m.replace` points to the stored root; no second root is created.

- [ ] **Step 5: Verify low-risk Matrix reaction -> HA -> panel state**

React `💡` as the allowed Matrix user, wait for HA state transition, then verify panel edit reflects actual HA state.

- [ ] **Step 6: Verify dangerous confirmation**

React `🔓`; assert target remains off. Locate confirmation reply, react `✅` from the same allowed user, then assert target becomes on. Wrong-sender and replay negatives remain mandatory unit/security tests; the real stack proves the positive encrypted end-to-end path.

- [ ] **Step 7: Verify outage coalescing**

During existing Synapse outage section, flip panel entity multiple times. After recovery, assert first successful panel update reflects only final desired state and no edit storm occurs.

- [ ] **Step 8: Verify HA restart root stability**

After HA restart, root event ID remains identical and no duplicate root appears.

- [ ] **Step 9: Verify redaction + explicit Repair UI**

Redact root, assert diagnostic state `needs_repair`, assert no automatic replacement, invoke Options Flow Repair, then assert exactly one new root.

- [ ] **Step 10: Add real-stack workflow step**

```yaml
- name: Verify encrypted Native Matrix Control panels
  run: python ci/scripts/matrix-control-e2e.py verify
```

Integrate with existing outage/restart sequence rather than starting a second stack.

- [ ] **Step 11: Run local helper/compile checks**

```bash
pytest -q tests/e2e/test_matrix_control_helpers.py
python -m compileall -q custom_components/matrix_extended ci/scripts
```

Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add ci/scripts/prepare-ha.sh ci/scripts/matrix-control-e2e.py \
  .github/workflows/test.yml tests/e2e/test_matrix_control_helpers.py
git commit -m "test: cover Matrix control panels on real HA stack"
```

---

### Task 13: Beta Release Semantics, Version and Final Verification

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `custom_components/matrix_extended/manifest.json`
- Modify: `CHANGELOG.md`
- Modify: `CHANGELOG.ru.md`
- Test: `tests/test_release_workflow.py`

- [ ] **Step 1: Write beta release RED contract test**

```python
workflow = Path(".github/workflows/release.yml").read_text()
assert "--prerelease" in workflow
assert "--latest" in workflow
assert "0.6.0b1" not in workflow
```

The logic must be generic, not hard-coded to one beta.

- [ ] **Step 2: Implement generic pre-release detection**

Use a Python stdlib regex that treats versions containing `aN`, `bN` or `rcN` suffixes as pre-release and emits a workflow output. Avoid adding a packaging dependency solely for release detection.

Stable path uses `gh release create ... --latest`; pre-release path uses `... --prerelease` and never `--latest`.

- [ ] **Step 3: Run entire fast gate before version bump**

```bash
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

Expected: PASS.

- [ ] **Step 4: Bump manifest to exact `0.6.0b1` and add bilingual changelog**

Notes must state existing-room limitation, reaction control, dangerous confirmation, persistence/recovery/pinning, GUI/YAML support, diagnostics, real-stack status, and that Widget is not included yet.

- [ ] **Step 5: Run full local release check**

```bash
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
python ci/scripts/build-release.py
```

Expected: PASS and `dist/matrix_extended-ha-install-v0.6.0b1.zip`.

- [ ] **Step 6: Open PR to `main`**

PR body links the design spec and plan, summarizes security boundaries, and states publication is blocked on all CI gates.

- [ ] **Step 7: Require exact-head green before merge**

Require Fast regression, Python 3.14 + E2EE manifest runtime, real HA/Synapse/Element, verified ZIP, Hassfest and HACS validation.

- [ ] **Step 8: Merge only after green and verify main CI on exact merge commit**

No completion claim until all main gates pass.

- [ ] **Step 9: Verify generated GitHub release**

Confirm tag `v0.6.0b1`, Pre-release flag, exact tested commit target, bilingual notes, install ZIP and SHA256, and ensure it is not Latest.

- [ ] **Step 10: Commit release-prep changes**

```bash
git add .github/workflows/release.yml \
  custom_components/matrix_extended/manifest.json \
  CHANGELOG.md CHANGELOG.ru.md tests/test_release_workflow.py
git commit -m "release: prepare Matrix Extended 0.6.0b1"
```

---

## Plan Self-Review Checklist

1. Every approved design requirement maps to a task above.
2. `SafeActionExecutionContext` resolves the existing camera-snapshot need without leaving a second executor.
3. Account room aliases are resolved before panel room-ID validation.
4. General incoming events may remain disabled while a narrow control-only reaction/redaction listener is active.
5. Pending confirmations are memory-only and cleared on reload/restart.
6. Lost/redacted roots never create automatic message storms; Repair is an explicit GUI action.
7. Pin failure is non-fatal, and re-pin attempts happen only at creation/startup recovery/repair.
8. HA state, not service-call success, drives visible panel state.
9. Panel outage handling never feeds state edits into the persistent normal-message outbox.
10. Widget support is only a stable interface boundary in b1; no Widget code is implemented.
11. Real-stack tests prove positive encrypted low-risk/dangerous paths; wrong-sender/replay are covered by unit/security tests.
12. Beta publication is Pre-release and not Latest.
