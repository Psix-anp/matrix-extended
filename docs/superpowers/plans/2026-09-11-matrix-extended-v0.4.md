# Matrix Extended v0.4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add room discovery/selection, room-specific notify entities, routing profiles, and persistent notification-key edits without weakening v0.3 E2EE/inbound security.

**Architecture:** Derive a read-only room directory from matrix-nio's synced `MatrixRoom` objects. Keep routing/notification-key logic in small pure modules, then wire them into the existing send service and HA entities. Persist notification-key → room/event mappings with Home Assistant `Store`; E2EE transport remains unchanged.

**Tech Stack:** Home Assistant 2026.9+, Python 3.13/3.14, matrix-nio[e2e] 0.26.0, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-matrix-extended-v0.3-interactive-design.md` plus the approved v0.4 scope in conversation.

## Global Constraints

- Preserve `Require E2EE` behavior before any media upload.
- Keep arbitrary inbound Matrix text unable to invoke HA services.
- `notification_key` edits only the primary text event; media remains explicit and is not silently re-uploaded.
- Route names must resolve to configured room targets; explicit `target` and `route` are mutually exclusive.
- Existing v0.3 config entries must load without migration prompts.

---

### Task 1: Room directory and routing core

**Files:**
- Create: `custom_components/matrix_extended/rooms.py`
- Create: `custom_components/matrix_extended/routing.py`
- Modify: `custom_components/matrix_extended/client.py`
- Test: `tests/test_v04_rooms_routing.py`

**Interfaces:**
- Produces `MatrixRoomInfo`, `MatrixClient.rooms_snapshot()`, `build_room_labels()`, `resolve_targets()`.

- [x] Write failing tests for room metadata, duplicate display-name labels, route resolution, target deduplication, and target+route rejection.
- [x] Run those tests and verify feature-absence failures.
- [x] Implement minimal pure room/routing logic and client snapshot adapter.
- [x] Run targeted tests and full regression suite.

### Task 2: Persistent notification-key registry

**Files:**
- Create: `custom_components/matrix_extended/notifications.py`
- Modify: `custom_components/matrix_extended/client.py`
- Test: `tests/test_v04_notifications.py`

**Interfaces:**
- Produces `NotificationKeyRegistry.get/set/dump`; `MatrixAccount.notification_registry` and `notification_store`.

- [x] Write failing tests for per-room event mappings, replacement, load/dump and invalid keys.
- [x] Run tests and verify failures.
- [x] Implement registry.
- [x] Run targeted tests and full regression suite.

### Task 3: Send service route + notification_key behavior

**Files:**
- Modify: `custom_components/matrix_extended/__init__.py`
- Modify: `custom_components/matrix_extended/const.py`
- Modify: `custom_components/matrix_extended/services.yaml`
- Test: `tests/test_v04_structure.py`

**Interfaces:**
- Adds `route` and `notification_key` fields to `matrix_extended.send`.

- [x] Write failing structure/API tests.
- [x] Run tests and verify failures.
- [x] Wire routing resolution, first-send registry storage, and subsequent `m.replace` edits.
- [x] Persist registry via Home Assistant `Store` after mapping changes.
- [x] Run full suite.

### Task 4: Room notify entities and default-room select

**Files:**
- Modify: `custom_components/matrix_extended/notify.py`
- Create: `custom_components/matrix_extended/select.py`
- Modify: `custom_components/matrix_extended/__init__.py`
- Modify: `custom_components/matrix_extended/client.py`
- Modify: `custom_components/matrix_extended/strings.json`
- Modify: `custom_components/matrix_extended/translations/en.json`
- Modify: `custom_components/matrix_extended/translations/ru.json`
- Test: `tests/test_v04_structure.py`

**Interfaces:**
- Adds one default notify entity plus one notify entity per joined room at setup; adds `select` for default room.

- [x] Extend failing structure tests for `Platform.SELECT`, room-specific notify and translations.
- [x] Implement entities using the room snapshot captured after initial full sync.
- [x] Persist default-room changes through the config entry and update runtime account immediately.
- [x] Run full suite.

### Task 5: Routing profiles options, migration-safe defaults, docs and release verification

**Files:**
- Modify: `custom_components/matrix_extended/config_flow.py`
- Modify: `custom_components/matrix_extended/manifest.json`
- Modify: `README.md`
- Modify: translation files
- Test: all tests

**Interfaces:**
- Adds `routing_profiles` option as a map of route name → room targets; bumps release to 0.4.0.

- [x] Add tests proving v0.3 entries can omit routes and version is 0.4.0.
- [x] Add options field and runtime default `{}`.
- [x] Document room entities, route syntax, notification-key semantics and E2EE behavior.
- [x] Run `pytest -q`, `compileall`, JSON/YAML validation, ZIP CRC and extracted-install compilation.
