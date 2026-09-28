# Matrix Native Widget 0.6.0b2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `0.6.0b2` with a graphical Matrix Widget that reuses Native Matrix Control security/runtime, communicates through narrowly scoped Matrix to-device events, exposes bounded HA controls, and keeps the reaction panel as a fallback.

**Architecture:** Add a versioned Widget protocol and session layer beside the existing control-panel manager, not a second control stack. The Widget sends only bounded intents to the exact Matrix Extended Matrix device ID; backend authorization, generation checks, confirmation, HA service construction, and execution remain local. State sent back to the Widget is a bounded projection of real HA state and is delivered only to active authorized subscriptions.

**Tech Stack:** Python 3.13/3.14, Home Assistant custom integration APIs, matrix-nio 0.26.0 E2EE, TypeScript, matrix-widget-api, pytest, Playwright/Chromium, Docker Compose, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-28-matrix-native-widget-design.md`

## Global Constraints

- Widget protocol event type is exactly `io.psix.matrix_extended.widget.v1` with `schema: 1`.
- Widget -> Matrix Extended traffic targets the exact integration `device_id`, never `*`.
- Matrix Extended -> authorized user state/result traffic may target `*`.
- No Home Assistant token, Matrix access token, arbitrary HA service/target/data, Jinja, or YAML may be supplied by Widget protocol payloads.
- Existing account `allowed_rooms` + `allowed_users` remain the outer authorization boundary; panel-level users may only narrow access.
- Stale panel `generation` is rejected; pending confirmations are memory-only and invalidated on restart/reload.
- Reaction-based Native Matrix Control remains fully functional when Widget support is disabled or unavailable.
- Generic automatic controls are limited to `light`, `switch`, `cover`, `climate`, `sensor`, `binary_sensor`, and `media_player`; `lock` and `alarm_control_panel` stay behind predefined confirmed panel actions for this beta.
- Widget heartbeat target: 30 seconds; subscription TTL: 90 seconds.
- Current stable real-stack gate for this plan is Home Assistant `2026.9.4`, Synapse `1.161.0`, Element Web `1.12.29`; RC lanes are non-blocking only.
- Integration version at release readiness is `0.6.0b2`; `0.5.8` remains stable until a later stable `0.6.0` release.

## Review Focus

- Forged `room_id`, `panel_id`, `entity_id`, `control`, or `generation` in a valid to-device envelope must be rejected without executing HA services — covered in Task 5 authorization tests.
- Duplicate/replayed `request_id` must not execute the same action twice — covered in Task 2 session/dedupe tests and Task 5 manager tests.
- A Widget opened on an unsupported Matrix client must fail visibly without breaking reaction controls — covered in Task 8 frontend tests and Task 9 real-stack fallback test.
- HA entities becoming unavailable or losing a supported feature at runtime must remove/disable that Widget control rather than emitting an invalid service call — covered in Task 4 adapter tests.
- Missing `vodozemac` / E2EE runtime support must produce a bounded startup diagnostic instead of leaking raw `ImportWarning` as the user-facing failure — covered in Task 6 preflight tests.

---

### Task 1: Versioned Widget Protocol Parser

**Files:**
- Create: `custom_components/matrix_extended/widget_protocol.py`
- Create: `tests/test_widget_protocol_v060b2.py`

**Interfaces:**
- Consumes: plain `Mapping[str, Any]` from Matrix to-device events.
- Produces: `WidgetRequest`, `WidgetSubscribeRequest`, `WidgetHeartbeatRequest`, `WidgetActionRequest`, `WidgetConfirmRequest`; `parse_widget_request(raw: Mapping[str, Any]) -> WidgetRequest`; `build_widget_message(...) -> dict[str, Any]`; constants `WIDGET_EVENT_TYPE` and `WIDGET_SCHEMA`.

- [ ] **Step 1: Write failing protocol tests**

Cover exact event type/schema, valid subscribe/heartbeat/action/confirm/cancel parsing, UUID-like bounded `request_id`, unknown op/schema rejection, missing room/panel/generation rejection, overlong identifiers rejection, and rejection of forbidden keys named `service`, `target`, `data`, `template`, or `yaml` anywhere in an action request.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `pytest -q tests/test_widget_protocol_v060b2.py`

Expected: FAIL because `widget_protocol.py` does not exist.

- [ ] **Step 3: Implement the minimal parser/dumper**

Implement exact public signatures above. Keep errors as `ValueError` with bounded non-secret messages; do not import Home Assistant in this module.

- [ ] **Step 4: Run the focused tests**

Run: `pytest -q tests/test_widget_protocol_v060b2.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/widget_protocol.py tests/test_widget_protocol_v060b2.py
git commit -m "feat: add versioned matrix widget protocol"
```

### Task 2: Ephemeral Widget Sessions, TTL, Revision and Replay Guard

**Files:**
- Create: `custom_components/matrix_extended/widget_sessions.py`
- Create: `tests/test_widget_sessions_v060b2.py`

**Interfaces:**
- Consumes: validated panel/user/room identities and request IDs.
- Produces: `WidgetSessionRegistry`; `subscribe(panel_id: str, room_id: str, user_id: str) -> WidgetSubscription`; `heartbeat(panel_id: str, user_id: str) -> bool`; `active_users(panel_id: str) -> tuple[str, ...]`; `next_revision(panel_id: str) -> int`; `accept_request(panel_id: str, user_id: str, request_id: str) -> bool`; `clear_panel(panel_id: str) -> None`.

- [ ] **Step 1: Write failing lifecycle tests**

Test immediate subscription, 30s heartbeat refresh, 90s expiry, no persistence API, monotonically increasing in-process revision, request-ID first-use `True` then replay `False`, pruning of old replay IDs, and panel clear on repair/reload.

- [ ] **Step 2: Run and confirm failure**

Run: `pytest -q tests/test_widget_sessions_v060b2.py`

Expected: FAIL because the registry does not exist.

- [ ] **Step 3: Implement `WidgetSessionRegistry`**

Use injected monotonic `now` for deterministic tests. Bound replay memory per `(panel_id, user_id)` and prune by TTL/count; do not write to Home Assistant `Store`.

- [ ] **Step 4: Run focused tests**

Run: `pytest -q tests/test_widget_sessions_v060b2.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/widget_sessions.py tests/test_widget_sessions_v060b2.py
git commit -m "feat: add ephemeral matrix widget sessions"
```

### Task 3: MatrixClient To-Device Transport

**Files:**
- Modify: `custom_components/matrix_extended/client.py`
- Create: `tests/test_client_widget_to_device_v060b2.py`

**Interfaces:**
- Consumes: `event_type`, target Matrix user/device, JSON-safe content, and matrix-nio callbacks.
- Produces: `MatrixClient.add_to_device_callback(callback: Any, event_filter: Any) -> None`; `MatrixClient.async_send_to_device(event_type: str, user_id: str, device_id: str, content: Mapping[str, Any]) -> None`.

- [ ] **Step 1: Write failing transport tests**

Assert callback registration delegates to matrix-nio; outbound payload targets `{user_id: {device_id: content}}`; exact integration device IDs are preserved; `*` is allowed only when caller explicitly passes it; matrix-nio error responses become `MatrixSendError`; transport exceptions become `MatrixConnectionError`.

- [ ] **Step 2: Run and confirm failure**

Run: `pytest -q tests/test_client_widget_to_device_v060b2.py`

Expected: FAIL because methods are missing.

- [ ] **Step 3: Implement the two client methods**

Use the matrix-nio 0.26.0 to-device API without changing crypto housekeeping or sync ownership. Keep the wrapper generic; authorization belongs in the Widget manager.

- [ ] **Step 4: Run focused and E2EE client tests**

Run: `pytest -q tests/test_client_widget_to_device_v060b2.py tests/test_client_e2ee.py tests/test_client_restore_login_io.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/client.py tests/test_client_widget_to_device_v060b2.py
git commit -m "feat: add matrix widget to-device transport"
```

### Task 4: Panel Widget Configuration and Bounded Entity Adapters

**Files:**
- Modify: `custom_components/matrix_extended/control_panels.py`
- Create: `custom_components/matrix_extended/widget_controls.py`
- Create: `tests/test_control_panels_widget_v060b2.py`
- Create: `tests/test_widget_controls_v060b2.py`

**Interfaces:**
- `PanelEntity` gains immutable `widget_controls: tuple[str, ...]` and `confirm_controls: tuple[str, ...]`, both default empty for backward compatibility.
- `ControlPanelDefinition` gains `widget_enabled: bool = False` and `widget_url: str | None = None`.
- `widget_controls.project_entity(panel_entity: PanelEntity, state: Any) -> dict[str, Any]` returns bounded state + effective controls.
- `widget_controls.build_control_action(panel_entity: PanelEntity, state: Any, control: str, value: Any) -> SafeActionDefinition` constructs only local bounded service calls.

- [ ] **Step 1: Write failing config compatibility tests**

Assert every `0.6.0b1` panel fixture still parses unchanged; YAML round-trip preserves Widget fields only when configured; unknown controls are rejected; domain-incompatible controls are rejected; `confirm_controls` must be a subset of enabled controls; invalid/non-HTTPS Widget URL is rejected except explicit localhost/test URLs used by CI.

- [ ] **Step 2: Write failing adapter tests**

Pin exact mappings for `light.toggle`, light brightness 0..100, `switch.toggle`, cover open/close/stop/position 0..100, climate target temp against min/max/step and hvac modes, read-only sensors, and media-player play/pause/previous/next/mute/volume. Assert unavailable entities and unsupported HA feature bits remove controls. Assert `lock`/`alarm_control_panel` generic control requests fail closed.

- [ ] **Step 3: Run and confirm failure**

Run: `pytest -q tests/test_control_panels_widget_v060b2.py tests/test_widget_controls_v060b2.py`

Expected: FAIL on missing fields/modules.

- [ ] **Step 4: Implement config fields and adapters**

Do not duplicate service execution: adapters return `SafeActionDefinition` and Task 5 executes through the existing `SafeActionExecutor`.

- [ ] **Step 5: Run focused plus existing panel tests**

Run: `pytest -q tests/test_control_panels_widget_v060b2.py tests/test_widget_controls_v060b2.py tests/test_config_flow_control_panels_v060.py tests/test_control_panels_v060.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/control_panels.py custom_components/matrix_extended/widget_controls.py tests/test_control_panels_widget_v060b2.py tests/test_widget_controls_v060b2.py
git commit -m "feat: add bounded widget entity controls"
```

### Task 5: Widget Control Manager, Authorization and Confirmation

**Files:**
- Create: `custom_components/matrix_extended/widget_manager.py`
- Modify: `custom_components/matrix_extended/control_panel_runtime.py`
- Modify: `custom_components/matrix_extended/control_panel_manager.py`
- Create: `tests/test_widget_manager_v060b2.py`

**Interfaces:**
- Consumes: `ControlPanelDefinition`, `ControlPanelRuntimeStore`, `WidgetSessionRegistry`, `SafeActionExecutor`, `MatrixClient`, account allowlists, and validated Widget requests.
- Produces: `WidgetControlManager.async_handle(sender: str, content: Mapping[str, Any]) -> None`; `WidgetControlManager.async_publish(panel_id: str) -> None`; `WidgetControlManager.async_close() -> None`; `diagnostics_snapshot() -> dict[str, Any]`.
- `ControlPanelManager` notifies Widget manager/listeners after actual HA state changes and calls `clear_panel()` when generation changes/repair occurs.

- [ ] **Step 1: Write failing subscribe/state tests**

Assert allowed sender+room+panel+current generation subscribes and immediately receives one complete state snapshot; unauthorized sender, forged room, disabled panel, `needs_repair`, and stale generation receive bounded rejection and create no session.

- [ ] **Step 2: Write failing action/replay tests**

Assert predefined panel actions resolve only local IDs; bounded entity controls resolve only configured entities/controls; duplicate `request_id` executes once; malicious service/target/data never reaches HA; service success returns `accepted` but final UI state changes only after actual HA state update/publish.

- [ ] **Step 3: Write failing confirmation tests**

Extend/reuse the current memory-only confirmation semantics so Widget confirmation is bound to panel, logical action/control identity, sender, generation, and a random confirmation ID for 30 seconds. Wrong sender, stale generation, timeout, cancel, duplicate confirm, repair and HA reload must not execute.

- [ ] **Step 4: Run and confirm failure**

Run: `pytest -q tests/test_widget_manager_v060b2.py`

Expected: FAIL because manager does not exist.

- [ ] **Step 5: Implement manager and minimal runtime hooks**

Use `SafeActionExecutor.async_execute(...)` for both panel actions and adapter-generated safe actions. State/result output targets authorized user device `*`; incoming requests have already been delivered only to the exact integration device but are still fully reauthorized.

- [ ] **Step 6: Run Widget + Native Control regression tests**

Run: `pytest -q tests/test_widget_manager_v060b2.py tests/test_control_panel_manager_v060.py tests/test_control_panel_runtime_v060.py tests/test_safe_actions_v060.py`

Expected: PASS with no reaction-panel regressions.

- [ ] **Step 7: Commit**

```bash
git add custom_components/matrix_extended/widget_manager.py custom_components/matrix_extended/control_panel_runtime.py custom_components/matrix_extended/control_panel_manager.py tests/test_widget_manager_v060b2.py
git commit -m "feat: route native widget control through safe actions"
```

### Task 6: Integration Wiring, To-Device Callback and E2EE Preflight

**Files:**
- Modify: `custom_components/matrix_extended/__init__.py`
- Modify: `custom_components/matrix_extended/client.py`
- Modify: `custom_components/matrix_extended/sensor.py`
- Create: `tests/test_setup_widget_v060b2.py`
- Create: `tests/test_e2ee_preflight_v060b2.py`

**Interfaces:**
- `MatrixAccount` gains `widget_manager: Any = None`.
- Setup registers a narrow to-device callback for `io.psix.matrix_extended.widget.v1` even if generic incoming-message automation handling is disabled, because Widget control has its own allowlist checks.
- Add `ensure_e2ee_runtime_available() -> None` (or equivalent) before constructing `AsyncClientConfig(encryption_enabled=True)`; raise a Matrix Extended specific bounded error when matrix-nio reports E2EE unavailable.

- [ ] **Step 1: Write failing setup tests**

Assert Widget manager is created only when at least one enabled panel has Widget enabled; callback filters only the Widget event type; unload closes Widget manager and leaves no tasks; existing reaction callbacks remain unchanged.

- [ ] **Step 2: Write failing E2EE preflight tests**

Monkeypatch matrix-nio encryption availability false and assert setup raises a Matrix Extended error containing `E2EE dependencies are unavailable` and `vodozemac`, not raw `ImportWarning`; normal runtime remains unchanged when E2EE is available.

- [ ] **Step 3: Run and confirm failure**

Run: `pytest -q tests/test_setup_widget_v060b2.py tests/test_e2ee_preflight_v060b2.py`

Expected: FAIL.

- [ ] **Step 4: Implement setup/unload/preflight and diagnostics fields**

Expose only non-secret Widget diagnostics: enabled panel count, active subscription count, last bounded error, protocol schema and local integration device ID.

- [ ] **Step 5: Run integration setup/client regressions**

Run: `pytest -q tests/test_setup_widget_v060b2.py tests/test_e2ee_preflight_v060b2.py tests/test_setup_control_panels_v060.py tests/test_client_e2ee.py tests/test_control_panel_diagnostics_v060.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/matrix_extended/__init__.py custom_components/matrix_extended/client.py custom_components/matrix_extended/sensor.py tests/test_setup_widget_v060b2.py tests/test_e2ee_preflight_v060b2.py
git commit -m "feat: wire native widget runtime and e2ee preflight"
```

### Task 7: Options Flow, Generated Widget Config and Translations

**Files:**
- Modify: `custom_components/matrix_extended/config_flow.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/en.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Modify: `tests/test_config_flow_control_panels_v060.py`
- Create: `tests/test_config_flow_widget_v060b2.py`

**Interfaces:**
- Options flow can enable Widget per panel, set `widget_url`, choose per-entity allowed controls and confirmation-required controls, and show generated config using account Matrix user ID + exact integration `device_id` + panel ID + room URL templating.
- No secret token appears in generated URL/config.

- [ ] **Step 1: Write failing flow tests**

Assert `0.6.0b1` panel edit still works; Widget disabled path requires no URL; enabled path validates URL/controls; generated configuration contains bot Matrix user ID and exact device ID but no access token/store key/password; Russian and English translation keys exist.

- [ ] **Step 2: Run and confirm failure**

Run: `pytest -q tests/test_config_flow_widget_v060b2.py tests/test_config_flow_control_panels_v060.py`

Expected: FAIL.

- [ ] **Step 3: Implement the smallest GUI extension**

Keep current Control Panels entry point; add Widget as a panel subflow rather than a new top-level integration concept.

- [ ] **Step 4: Run config/translation tests**

Run: `pytest -q tests/test_config_flow_widget_v060b2.py tests/test_config_flow_control_panels_v060.py tests/test_settings_ui_contract.py tests/test_integration_structure.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/config_flow.py custom_components/matrix_extended/strings.json custom_components/matrix_extended/translations/en.json custom_components/matrix_extended/translations/ru.json tests/test_config_flow_control_panels_v060.py tests/test_config_flow_widget_v060b2.py
git commit -m "feat: add native widget options flow"
```

### Task 8: Static TypeScript Widget MVP

**Files:**
- Create: `widget/package.json`
- Create: `widget/tsconfig.json`
- Create: `widget/src/index.ts`
- Create: `widget/src/matrix.ts`
- Create: `widget/src/protocol.ts`
- Create: `widget/src/model.ts`
- Create: `widget/src/render.ts`
- Create: `widget/src/styles.css`
- Create: `widget/src/i18n/en.ts`
- Create: `widget/src/i18n/ru.ts`
- Create: `widget/tests/protocol.test.ts`
- Create: `widget/tests/render.test.ts`

**Interfaces:**
- Frontend requests only `org.matrix.msc3819.send.to_device:io.psix.matrix_extended.widget.v1` and `org.matrix.msc3819.receive.to_device:io.psix.matrix_extended.widget.v1`.
- `matrix.ts` targets exact configured integration user/device for outbound requests.
- `render.ts` renders only controls named by backend snapshots.

- [ ] **Step 1: Create package/test scaffold and failing protocol tests**

Pin `matrix-widget-api` to the current compatible `1.18.x` line and use a small test runner/build tool. Tests assert capability strings, exact target device use, subscribe/heartbeat schedule, stale revision ignore, request/result correlation and unsupported-capability state.

- [ ] **Step 2: Add failing render tests**

Assert read-only sensors, light/switch controls, cover/climate controls, media player controls, unavailable-state disabling, confirmation dialog with 30s timeout, RU/EN labels, and absence of controls not supplied by server snapshot.

- [ ] **Step 3: Run and confirm failure**

Run: `cd widget && npm ci && npm test`

Expected: FAIL before implementation.

- [ ] **Step 4: Implement minimal framework-free Widget**

Use TypeScript + DOM APIs only for MVP; no React/Vue dependency. Support dark/light via CSS media query, keyboard focus, touch-sized controls, visible connection/capability errors, and reaction-panel fallback text.

- [ ] **Step 5: Build and test**

Run: `cd widget && npm test && npm run build`

Expected: PASS and static output under `widget/dist/`.

- [ ] **Step 6: Commit**

```bash
git add widget
git commit -m "feat: add native matrix widget frontend"
```

### Task 9: Real-Stack Widget E2E, Compatibility Pins and Release Packaging

**Files:**
- Modify: `compose.test.yml`
- Modify: `.github/workflows/test.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `ci/scripts/bootstrap-matrix.py`
- Modify: `ci/scripts/prepare-ha.sh`
- Modify: `ci/scripts/element-e2e.py`
- Create: `ci/scripts/widget-e2e.py`
- Create: `tests/e2e/test_widget_profile_contract.py`
- Modify: `ci/scripts/build-release.py`
- Modify: `requirements-test.txt` if Playwright/Node helper dependencies require it.

**Interfaces:**
- Blocking stable lane: HA `2026.9.4` + Synapse `1.161.0` + Element Web `1.12.29`.
- Widget browser E2E proves actual Element capability grant + to-device round-trip + HA state/action round-trip.
- Package job outputs existing HA install ZIP plus `dist/matrix_extended-widget-v0.6.0b2.zip` and SHA256.

- [ ] **Step 1: Update stable stack pins and contract tests**

Adjust job names/images/assertions to the exact stable versions above. Keep any Synapse `1.162.0rc1` / Element `1.12.30-rc.1` experiment in a separate non-blocking job only if it can be added without slowing the required release gate materially.

- [ ] **Step 2: Add Widget E2E helper and failing browser scenario**

The scenario must: open a room Widget in Element; verify capabilities; subscribe; render an HA entity state; toggle a harmless test entity; observe actual HA state then new Widget snapshot; exercise a confirmed action; attempt stale generation/replay and verify rejection; restart HA and resubscribe; verify reaction fallback still works.

- [ ] **Step 3: Add outage behavior**

Stop Synapse while Widget is open, flip HA state, restart Synapse, resubscribe/heartbeat and assert Widget receives one current snapshot rather than replaying intermediate control state. Assert no stale action is executed after reconnect.

- [ ] **Step 4: Extend package/release workflow**

Build Widget before packaging, zip only static distributable files, generate SHA256, upload both Widget and HA install artifacts, and keep pre-release handling from `0.6.0b1`.

- [ ] **Step 5: Run local/CI-equivalent gates**

Run:

```bash
pytest -q
cd widget && npm ci && npm test && npm run build
python ci/scripts/validate-source.py
python ci/scripts/build-release.py
```

Then run the full GitHub `Matrix Extended tests` workflow and require fast, manifest runtime, real stack, and package jobs green.

- [ ] **Step 6: Commit**

```bash
git add compose.test.yml .github/workflows/test.yml .github/workflows/release.yml ci tests/e2e requirements-test.txt
git commit -m "test: gate native widget on real matrix stack"
```

### Task 10: Documentation, Version and Beta Release Readiness

**Files:**
- Modify: `custom_components/matrix_extended/manifest.json`
- Modify: `README.md`
- Modify: `README.ru.md`
- Modify: `CHANGELOG.md`
- Modify: `CHANGELOG.ru.md`
- Create: `docs/WIDGET.md`
- Create: `docs/WIDGET.ru.md`
- Modify: `docs/CONTROL_PANELS.md`
- Modify: `docs/CONTROL_PANELS.ru.md`
- Modify: `docs/TESTING.md`
- Modify: `docs/TESTING.ru.md`

**Interfaces:**
- Version becomes exactly `0.6.0b2` only after Tasks 1-9 pass.
- Docs explain supported clients/capabilities, self-hosting, exact-device config, security model, supported domains, reaction fallback, troubleshooting, and no-token architecture.

- [ ] **Step 1: Write/update documentation from implemented behavior**

Do not document speculative auto-install if Task 7/9 ships manual Widget installation. Include a troubleshooting section for unsupported capability, wrong device ID, expired subscription, stale generation, `needs_repair`, and missing E2EE runtime.

- [ ] **Step 2: Bump version and changelogs**

Set manifest `0.6.0b2`, update README badges, English/Russian changelogs, and mark this as pre-release/beta.

- [ ] **Step 3: Run final verification**

Run all fast tests, manifest runtime Python 3.14 gate, Widget tests/build, HACS validation, Hassfest, full real-stack E2E, and verified package checks. Confirm release artifacts contain both HA install ZIP and Widget ZIP with SHA256 files.

- [ ] **Step 4: Open/refresh the draft PR**

PR title: `0.6.0b2 Native Matrix Widget`

PR body must list implemented scope, explicit deferred scope, stable stack versions, exact full-CI run URL, and state that `0.5.8` remains stable while `0.6.0b2` is a pre-release.

- [ ] **Step 5: Commit**

```bash
git add custom_components/matrix_extended/manifest.json README.md README.ru.md CHANGELOG.md CHANGELOG.ru.md docs
git commit -m "release: prepare matrix extended 0.6.0b2"
```

## Plan Self-Review

- Spec coverage: protocol, exact-device targeting, subscriptions, bounded state, entity adapters, confirmation, frontend, self-hosting, options flow, E2EE preflight, diagnostics, stable-stack E2E, packaging and docs all map to Tasks 1-10.
- Type consistency: protocol -> session -> client transport -> adapter -> manager -> setup -> GUI/frontend -> E2E interfaces are named once and reused.
- Backward compatibility: `PanelEntity`/`ControlPanelDefinition` fields default to disabled/empty so `0.6.0b1` panel configs remain valid; reaction control has explicit regression gates in Tasks 4, 5, 6 and 9.
- Security: exact integration `device_id`, fail-closed reauthorization, generation checks, dedupe, bounded parameters and memory-only confirmation are each directly tested.
- Release discipline: manifest version changes only in Task 10 after the implementation and real-stack gates are green.
