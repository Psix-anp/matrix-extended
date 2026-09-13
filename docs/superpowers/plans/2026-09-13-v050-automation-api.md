# Matrix Extended 0.5 Automation API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add delivery observability, richer Matrix message semantics, inbound relation events, safer persistent interaction actions, and bounded inbound-media storage.

**Architecture:** Keep the existing `MatrixAccount`/`MatrixClient` transport boundary. Extend pure content/action/storage helpers first, then wire them through service schemas and the receiver. New behavior remains opt-in except for delivery observability and conservative media cleanup defaults.

**Tech Stack:** Python 3.13, Home Assistant 2026.9.2, matrix-nio 0.26.0, Synapse 1.160.0, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-v050-automation-api-design.md`

## Global Constraints

- Preserve all existing `send`, `reply`, `react`, `edit`, `redact`, notify, E2EE, routing, notification-key, and reconnect behavior.
- Do not execute arbitrary Matrix text/YAML/Jinja as Home Assistant actions.
- Do not add a Markdown dependency; use a small escaped subset renderer.
- Keep all inbound media cleanup scoped to the integration account directory.
- Keep Matrix transaction IDs stable across queued retry.
- Validate against Home Assistant 2026.9.2 + Synapse 1.160.0 real-stack CI.

---

### Task 1: Message semantics helpers

**Files:**
- Modify: `custom_components/matrix_extended/content.py`
- Test: `tests/test_content.py`

**Interfaces:**
- Produces: `render_markdown(message: str) -> str`
- Produces: `build_mentions(user_ids: Sequence[str] | None, room: bool = False) -> dict[str, Any]`
- Extends: `build_text_content`, `build_reply_content`, `build_edit_content` with `msgtype` and mentions where applicable.

- [ ] **Step 1: Write failing tests** for `m.notice`, `m.emote`, escaped Markdown, links/code/bold/italic, deduplicated `m.mentions`, reply mentions, and edit msgtype.
- [ ] **Step 2: Run** `pytest -q tests/test_content.py` and confirm the new tests fail.
- [ ] **Step 3: Implement** safe Markdown rendering using `html.escape` plus conservative regex substitutions, validate `msgtype in {text, notice, emote}`, and attach `m.mentions` only when non-empty.
- [ ] **Step 4: Run** `pytest -q tests/test_content.py` and confirm pass.
- [ ] **Step 5: Commit** `feat: add Matrix message semantics helpers`.

### Task 2: Reaction actions v2

**Files:**
- Modify: `custom_components/matrix_extended/actions.py`
- Modify: `custom_components/matrix_extended/__init__.py`
- Test: `tests/test_v03_actions.py`

**Interfaces:**
- Extends action input with `expires_in: int`, `max_uses: int`, `allowed_users: list[str]`.
- Extends `ReactionActionRegistry.consume(..., sender: str | None = None)`.

- [ ] **Step 1: Write failing tests** for persisted expiry, unauthorized sender non-consumption, multiple uses, expiry pruning, and loading legacy stored actions.
- [ ] **Step 2: Run** `pytest -q tests/test_v03_actions.py` and confirm failure.
- [ ] **Step 3: Implement** absolute expiry timestamps, remaining uses, allowlist checks, bounded validation, and JSON-safe persistence.
- [ ] **Step 4: Wire** `sender=event.sender` into receiver consumption and expand `_ACTION_SCHEMA`.
- [ ] **Step 5: Run** `pytest -q tests/test_v03_actions.py tests/test_receiver_behavior.py` and confirm pass.
- [ ] **Step 6: Commit** `feat: harden persistent reaction actions`.

### Task 3: Inbound edit/redaction and richer payloads

**Files:**
- Modify: `custom_components/matrix_extended/const.py`
- Modify: `custom_components/matrix_extended/incoming.py`
- Modify: `custom_components/matrix_extended/receiver.py`
- Test: `tests/test_v03_incoming.py`
- Test: `tests/test_receiver_behavior.py`

**Interfaces:**
- Produces events `matrix_extended_edit`, `matrix_extended_redaction`.
- Produces helper `extract_replacement(source) -> tuple[str | None, Mapping[str, Any] | None]`.

- [ ] **Step 1: Write failing tests** for replacement detection, redaction callback, room/sender metadata, and media size/dimensions/duration.
- [ ] **Step 2: Run** receiver/incoming tests and confirm failure.
- [ ] **Step 3: Implement** replacement extraction; route replacement text to edit event instead of normal message/reply; register redaction callback using matrix-nio redaction event support; enrich base/media payloads from already-synced room/event data without network calls.
- [ ] **Step 4: Run** receiver/incoming tests and confirm pass.
- [ ] **Step 5: Commit** `feat: expose Matrix edits and redactions`.

### Task 4: Delivery result model and lifecycle events

**Files:**
- Modify: `custom_components/matrix_extended/const.py`
- Modify: `custom_components/matrix_extended/__init__.py`
- Test: `tests/test_reconnect_workflow.py`
- Create: `tests/test_delivery_behavior.py`

**Interfaces:**
- `_async_execute_send(...) -> list[dict[str, Any]]` where each event entry has `room_id`, `event_id`, `kind`, optional `media_index`.
- `_async_handle_send(...) -> dict[str, Any]` returns `delivery_id`, `status`, `events`.
- Fires `matrix_extended_delivery`.

- [ ] **Step 1: Write failing unit tests** for sent response, queued response, lifecycle payloads, and dropped queued delivery.
- [ ] **Step 2: Run** targeted tests and confirm failure.
- [ ] **Step 3: Refactor** `_async_execute_send` to collect event IDs from text and media sends without changing transaction IDs.
- [ ] **Step 4: Add** a small delivery-event helper and fire `sent/queued/failed/dropped` exactly as specified.
- [ ] **Step 5: Register** `send` with optional Home Assistant service responses using `SupportsResponse.OPTIONAL`; leave other services response-less.
- [ ] **Step 6: Run** targeted tests and confirm pass.
- [ ] **Step 7: Commit** `feat: report Matrix delivery lifecycle`.

### Task 5: Service schemas for msgtype, Markdown, and mentions

**Files:**
- Modify: `custom_components/matrix_extended/const.py`
- Modify: `custom_components/matrix_extended/__init__.py`
- Modify: `custom_components/matrix_extended/services.yaml`
- Test: `tests/test_integration_v02_structure.py`
- Create: `tests/test_service_schema_v05.py`

**Interfaces:**
- Adds `msgtype`, `mention_users`, `mention_room`, `format: markdown` to `send`; `msgtype`/format/mentions to `reply`; `msgtype`/format to `edit`.

- [ ] **Step 1: Write failing schema/structure tests** covering defaults, invalid msgtypes, Markdown rendering wiring, mentions, and notification-key edit non-remention behavior.
- [ ] **Step 2: Run** targeted tests and confirm failure.
- [ ] **Step 3: Extend constants/schemas** and use a single formatting helper that returns plain `body` plus optional `formatted_body`.
- [ ] **Step 4: Update services metadata** with selectors/descriptions for new fields and delivery response behavior.
- [ ] **Step 5: Run** targeted tests and confirm pass.
- [ ] **Step 6: Commit** `feat: add Markdown mentions and message types`.

### Task 6: Inbound media retention and purge service

**Files:**
- Create: `custom_components/matrix_extended/retention.py`
- Modify: `custom_components/matrix_extended/const.py`
- Modify: `custom_components/matrix_extended/config_flow.py`
- Modify: `custom_components/matrix_extended/receiver.py`
- Modify: `custom_components/matrix_extended/__init__.py`
- Modify: `custom_components/matrix_extended/services.yaml`
- Test: `tests/test_config_flow_ui_schema.py`
- Create: `tests/test_retention.py`

**Interfaces:**
- `cleanup_media_directory(path: Path, *, retention_days: int, max_bytes: int, now: float | None = None) -> CleanupResult`.
- Service `matrix_extended.purge_media` returns `removed_files`, `removed_bytes` when response requested.

- [ ] **Step 1: Write failing tests** for age deletion, quota deletion oldest-first, directory scoping, purge counts, and option selectors/defaults.
- [ ] **Step 2: Run** targeted tests and confirm failure.
- [ ] **Step 3: Implement** pure retention helper with no symlink traversal and deterministic oldest-first quota cleanup.
- [ ] **Step 4: Add options** (`7` days, `256` MiB defaults) and account runtime retention configuration.
- [ ] **Step 5: Invoke cleanup** at setup and after successful media writes via executor; add `purge_media` service.
- [ ] **Step 6: Run** targeted tests and confirm pass.
- [ ] **Step 7: Commit** `feat: bound inbound Matrix media storage`.

### Task 7: Real-stack coverage and documentation

**Files:**
- Modify: `ci/scripts/ha-e2e.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `custom_components/matrix_extended/manifest.json`

**Interfaces:**
- Release version becomes `0.5.0`.

- [ ] **Step 1: Extend real-stack E2E** so the encrypted send requests service response data and asserts `status == sent`, at least one event ID, and a `matrix_extended_delivery` event observed through HA.
- [ ] **Step 2: Update README** with delivery response/event, msgtype, Markdown, mentions, edit/redaction events, reaction-action TTL/users/uses, and retention/purge examples.
- [ ] **Step 3: Update CHANGELOG and manifest** to `0.5.0`.
- [ ] **Step 4: Run full CI**: source validation, compile, pytest, real HA+Synapse, package gate.
- [ ] **Step 5: Commit** `release: prepare Matrix Extended 0.5.0`.

### Task 8: Final verification

**Files:** none unless verification exposes a defect.

- [ ] **Step 1: Verify** every requirement in the design spec maps to passing tests.
- [ ] **Step 2: Verify** existing 0.4.x tests remain green.
- [ ] **Step 3: Inspect HA logs** for event-loop blocking, leaked tasks, and reconnect regressions.
- [ ] **Step 4: Keep the PR draft until all mandatory checks are green; then mark ready for review.**
