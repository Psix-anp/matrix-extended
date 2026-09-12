# Matrix Extended v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver a HACS-compatible Home Assistant Matrix notification integration with rich media and a universal send action.

**Architecture:** Keep Matrix transport, media resolution, and Matrix event construction separate. Use a Config Flow that exchanges a password for an access token, a modern `NotifyEntity` for simple notifications, and a custom action for richer media.

**Tech Stack:** Python 3.14+, Home Assistant 2026.9+, matrix-nio 0.26.0, Pillow, aiohttp via Home Assistant.

**Spec:** `docs/superpowers/specs/2026-09-10-matrix-extended-design.md`

## Global Constraints
- Domain is exactly `matrix_extended`.
- Do not patch or shadow Home Assistant Core's `matrix` integration.
- Password is never persisted after Config Flow login.
- Local paths must pass Home Assistant `is_allowed_path`.
- Maximum resolved attachment size is 128 MiB.
- E2EE is out of scope for v0.1.

---

### Task 1: Matrix content builder
**Files:** Create `custom_components/matrix_extended/content.py`; Test `tests/test_content.py`.
**Interfaces:** Produces `build_text_content`, `build_media_content`, `infer_media_type`, and `validate_media_item_shape`.
- [x] Write failing tests for text/HTML threads, caption+filename semantics, video metadata/thumbnails, MIME type inference, and source exclusivity.
- [x] Run tests and confirm failure because implementation is absent.
- [x] Implement the pure helpers.
- [x] Run tests and confirm pass.

### Task 2: Home Assistant integration skeleton and Matrix client
**Files:** Create manifest, constants, `client.py`, `config_flow.py`, strings/translations.
**Interfaces:** Produces credential validation, restored Matrix client sessions, room resolution, upload, and room send.
- [x] Add implementation following current HA Config Flow and matrix-nio 0.26 APIs.
- [x] Syntax-compile package.

### Task 3: Media resolver and send action
**Files:** Create `media.py`, `__init__.py`, `services.yaml`.
**Interfaces:** Consumes content/client helpers; produces `matrix_extended.send`.
- [x] Resolve camera/image/path/url/media_source inputs and metadata.
- [x] Validate service media lists and account/target selection.
- [x] Upload thumbnails/media and preserve send order.
- [x] Syntax-compile package and run unit tests.

### Task 4: Notify entity and packaging
**Files:** Create `notify.py`, `README.md`, `hacs.json`, `.gitignore`.
**Interfaces:** Produces one modern `notify` entity per account and installable ZIP.
- [x] Implement notify entity using default room.
- [x] Document installation, limitations, and YAML examples.
- [x] Run pytest and compileall.
- [x] Build ZIP with `custom_components/matrix_extended` at the expected path.
