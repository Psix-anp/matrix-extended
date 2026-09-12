# Matrix Extended v0.4.1 Real HA + Synapse Test Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import the proven Matrix Extended 0.4.1 source baseline into GitHub and add a reproducible pre-merge test pipeline that exercises the integration against Home Assistant 2026.9.2 and Synapse 1.160.0 before any release is published.

**Architecture:** Keep the existing 0.4.1 integration and its 129-test suite intact. Add a fast source/regression gate plus an isolated real-stack gate: Synapse runs as a disposable Docker service, while Home Assistant is exercised with its real 2026.9.2 core runtime and the checked-out custom component; CI bootstraps Matrix users/rooms automatically and validates actual Matrix Client-Server API effects. Preserve logs and sanitized diagnostics on failure.

**Tech Stack:** Python 3.13, Home Assistant Core 2026.9.2, matrix-nio[e2e] 0.26.0, Pillow 12.3.0, Synapse 1.160.0, pytest, GitHub Actions, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-12-matrix-extended-test-harness-design.md`

## Global Constraints

- Baseline is `matrix_extended-v0.4.1-source.zip`, SHA-256 `3de0b517ad36b590fc1f4a5110d3b109adc33a8dbe73a543eb8cb4c80305defc`.
- Install artifact is `matrix_extended-ha-install-v0.4.1.zip`, SHA-256 `425116cd91e779633cb0c3b4ba7205ba4fe77e84749fa5581722764fcfe42c73`.
- Baseline local regression result is 129 passed.
- The 22 files under `custom_components/matrix_extended` are byte-identical between source and install artifacts.
- Preserve version `0.4.1` until a behavior change is intentionally released.
- Keep `Require E2EE` secure-by-default semantics.
- No inbound arbitrary Matrix text may execute HA services.
- No access token, password, crypto key, Authorization header, or decrypted private payload may be uploaded as CI artifact.
- Development occurs on a feature branch; `main` is updated only after all required gates pass.

---

### Task 1: Import and prove the 0.4.1 baseline

**Files:**
- Create/import: `custom_components/matrix_extended/**`
- Create/import: `tests/test_*.py`
- Create/import: `README.md`, `hacs.json`, `.gitignore`
- Create/import: prior `docs/superpowers/specs/**` and `docs/superpowers/plans/**`
- Keep: `MUTATION_TESTING.md`
- Exclude generated artifacts: `.pytest_cache/**`, `__pycache__/**`, `*.pyc`, `mutation-results.json`, `mutation-client-results.json`, `mutation-media-results.json`

**Interfaces:**
- Produces the exact 0.4.1 runtime and regression baseline used by all later tasks.

- [ ] **Step 1: Import the source tree without generated cache/results**

Use the library source archive as authoritative input. Preserve all runtime/test/document files and file contents exactly, except the explicitly excluded generated artifacts.

- [ ] **Step 2: Run the baseline suite**

Run:

```bash
pytest -q
```

Expected:

```text
129 passed
```

- [ ] **Step 3: Run syntax/data validation**

Run:

```bash
python -m compileall -q custom_components/matrix_extended
python - <<'PY'
import json
from pathlib import Path
root = Path('custom_components/matrix_extended')
assert json.loads((root / 'manifest.json').read_text())['version'] == '0.4.1'
for path in [root / 'manifest.json', root / 'strings.json', *sorted((root / 'translations').glob('*.json'))]:
    json.loads(path.read_text())
print('json-ok')
PY
```

Expected: exit 0 and `json-ok`.

- [ ] **Step 4: Commit baseline import**

```bash
git add custom_components tests docs README.md hacs.json .gitignore MUTATION_TESTING.md
git commit -m "chore: import Matrix Extended 0.4.1 baseline"
```

---

### Task 2: Add deterministic fast CI gate

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `requirements-test.txt`
- Create: `ci/scripts/validate-source.py`

**Interfaces:**
- Produces GitHub Actions job `fast`.
- `validate-source.py` exits non-zero on cache/build artifacts, invalid JSON, wrong version, or missing required package files.

- [ ] **Step 1: Write source validation test first**

Create `ci/scripts/validate-source.py` that asserts:

```python
REQUIRED = {
    '__init__.py', 'manifest.json', 'config_flow.py', 'client.py',
    'receiver.py', 'media.py', 'notify.py', 'services.yaml',
    'strings.json', 'translations/en.json', 'translations/ru.json',
}
FORBIDDEN_PARTS = {'__pycache__', '.pytest_cache'}
FORBIDDEN_SUFFIXES = {'.pyc', '.pyo'}
```

It must also assert manifest version `0.4.1` and valid JSON resources.

- [ ] **Step 2: Run validator before CI wiring**

Run:

```bash
python ci/scripts/validate-source.py
```

Expected: PASS on the clean imported tree.

- [ ] **Step 3: Add test dependencies**

`requirements-test.txt` contains pinned runtime dependencies used by the baseline plus pytest:

```text
pytest
matrix-nio[e2e]==0.26.0
Pillow==12.3.0
```

- [ ] **Step 4: Add `fast` GitHub Actions job**

The job uses Python 3.13 and runs:

```bash
python -m pip install -r requirements-test.txt
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

- [ ] **Step 5: Commit fast gate**

```bash
git add .github/workflows/test.yml requirements-test.txt ci/scripts/validate-source.py
git commit -m "ci: add Matrix Extended regression gate"
```

---

### Task 3: Add disposable Synapse service and Matrix bootstrap

**Files:**
- Create: `compose.test.yml`
- Create: `ci/synapse/homeserver.yaml`
- Create: `ci/scripts/wait-http.py`
- Create: `ci/scripts/bootstrap-matrix.py`
- Test: `tests/e2e/test_matrix_bootstrap_contract.py`

**Interfaces:**
- Synapse URL inside CI: `http://127.0.0.1:8008`.
- Test server name: `matrix.test`.
- Test users: `@ha_bot:matrix.test` and `@ha_user:matrix.test`.
- Bootstrap output file: `.ci/matrix-env.json` containing homeserver URL, user IDs, ephemeral access tokens, room ID, room alias, and generated passwords.

- [ ] **Step 1: Write bootstrap contract test**

The test feeds deterministic fake Client-Server API responses into the bootstrap helper and asserts the returned document contains exactly:

```python
{
    'homeserver', 'bot_user_id', 'bot_access_token',
    'user_user_id', 'user_access_token', 'room_id', 'room_alias'
}
```

and never prints access tokens to stdout.

- [ ] **Step 2: Run contract test and verify RED**

```bash
pytest -q tests/e2e/test_matrix_bootstrap_contract.py
```

Expected: FAIL because bootstrap helper does not exist.

- [ ] **Step 3: Implement Synapse config**

Use Synapse 1.160.0 with SQLite, federation disabled for the disposable test server, registration shared secret supplied only through CI/runtime configuration, listeners on 8008, and no public report stats.

- [ ] **Step 4: Implement bootstrap helper**

`bootstrap-matrix.py` must:

1. wait for `/_matrix/client/versions`;
2. register/login bot and user;
3. create an encrypted room (`m.room.encryption` with `m.megolm.v1.aes-sha2`);
4. invite and join the second user;
5. write `.ci/matrix-env.json` with mode 0600;
6. print only user IDs/room ID, never credentials.

- [ ] **Step 5: Run real Synapse smoke where Docker is available**

```bash
docker compose -f compose.test.yml up -d synapse
python ci/scripts/wait-http.py http://127.0.0.1:8008/_matrix/client/versions
python ci/scripts/bootstrap-matrix.py
```

Expected: encrypted room created and `.ci/matrix-env.json` present.

- [ ] **Step 6: Commit Synapse harness**

```bash
git add compose.test.yml ci/synapse ci/scripts/wait-http.py ci/scripts/bootstrap-matrix.py tests/e2e/test_matrix_bootstrap_contract.py
git commit -m "test: add disposable Synapse harness"
```

---

### Task 4: Run Matrix Extended inside real Home Assistant Core

**Files:**
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_setup_lifecycle.py`
- Modify: `requirements-test.txt`
- Modify: `.github/workflows/test.yml`

**Interfaces:**
- Uses Home Assistant Core 2026.9.2 test runtime.
- Creates a real `ConfigEntry` through Home Assistant's config-entry APIs using the Matrix credentials from `.ci/matrix-env.json`.
- Produces fixture `matrix_account` after `async_setup_entry` completes against real Synapse.

- [ ] **Step 1: Write failing lifecycle test**

Test sequence:

```python
entry = MockConfigEntry(domain='matrix_extended', data=matrix_entry_data)
entry.add_to_hass(hass)
assert await hass.config_entries.async_setup(entry.entry_id)
await hass.async_block_till_done()
assert entry.state is ConfigEntryState.LOADED
assert await hass.config_entries.async_unload(entry.entry_id)
assert entry.state is ConfigEntryState.NOT_LOADED
```

Also assert no `matrix_extended` background sync task remains after unload.

- [ ] **Step 2: Add HA test dependencies**

Pin Home Assistant to `2026.9.2` and use the matching `pytest-homeassistant-custom-component` release compatible with that core. Do not loosen Matrix runtime pins from the manifest.

- [ ] **Step 3: Run lifecycle test against real Synapse**

Expected: setup connects to Synapse, performs full sync/E2EE housekeeping, registers entities/services/listener, unload closes the client and cancels listener.

- [ ] **Step 4: Add CI `e2e` job dependency on `fast`**

The `e2e` job starts Synapse, bootstraps Matrix, installs HA/test dependencies, then runs only `tests/e2e/`.

- [ ] **Step 5: Commit HA lifecycle harness**

```bash
git add tests/e2e requirements-test.txt .github/workflows/test.yml
git commit -m "test: run Matrix Extended against Home Assistant and Synapse"
```

---

### Task 5: Verify real outbound Matrix behavior

**Files:**
- Create: `tests/e2e/test_outbound.py`
- Create: `tests/e2e/matrix_api.py`

**Interfaces:**
- `MatrixApi.wait_for_event(room_id, predicate, timeout=...) -> dict` reads the second user's `/sync` stream from real Synapse.

- [ ] **Step 1: Write text-send E2E test**

Call Matrix Extended's actual send path with a unique marker:

```python
marker = f'e2e-{uuid4()}'
await hass.services.async_call(
    'matrix_extended', 'send',
    {'message': marker}, blocking=True,
)
event = await matrix_api.wait_for_event(room_id, lambda e: e.get('content', {}).get('body') == marker)
assert event['type'] == 'm.room.message'
```

Because the room is encrypted, verify the receiving Matrix client can decrypt the event rather than asserting plaintext at the homeserver database level.

- [ ] **Step 2: Write reply/reaction/edit/redact E2E coverage**

Exercise the real service endpoints and verify Matrix relations/events from the second client.

- [ ] **Step 3: Write notification-key update E2E test**

Send twice with the same `notification_key`; assert the second operation emits `m.replace` referencing the first event instead of creating an unrelated notification message.

- [ ] **Step 4: Run outbound E2E suite**

```bash
pytest -q tests/e2e/test_outbound.py
```

Expected: all scenarios PASS against Synapse.

- [ ] **Step 5: Commit outbound tests**

```bash
git add tests/e2e/test_outbound.py tests/e2e/matrix_api.py
git commit -m "test: verify real Matrix outbound behavior"
```

---

### Task 6: Verify inbound events, media and security boundaries

**Files:**
- Create: `tests/e2e/test_inbound.py`
- Create: `tests/e2e/test_media.py`

**Interfaces:**
- Uses the second Matrix user to send encrypted events/media into the room and Home Assistant bus listeners to observe `matrix_extended_message`, `matrix_extended_reply`, `matrix_extended_reaction`, and `matrix_extended_media`.

- [ ] **Step 1: Write inbound message/reply/reaction tests**

Assert allowed user + allowed room events fire the expected HA events exactly once.

- [ ] **Step 2: Write deny-path tests**

Create a non-allowlisted room/user event and assert no Home Assistant event/action is emitted.

- [ ] **Step 3: Write encrypted media test**

Upload a small deterministic fixture through the second Matrix client, send it encrypted, assert Matrix Extended downloads/decrypts it under the integration incoming directory, and verify SHA-256 of the recovered bytes.

- [ ] **Step 4: Verify arbitrary Matrix text cannot invoke HA services**

Send text resembling YAML/service commands and assert no service call occurs unless the event is an explicitly registered reaction action for the exact original event ID.

- [ ] **Step 5: Commit inbound/media coverage**

```bash
git add tests/e2e/test_inbound.py tests/e2e/test_media.py
git commit -m "test: verify inbound Matrix security and media"
```

---

### Task 7: Reproduce and eliminate aiohttp/server and lifecycle failures

**Files:**
- Create: `tests/e2e/test_resilience.py`
- Create: `ci/scripts/assert-clean-ha-log.py`
- Modify only the runtime file(s) implicated by the reproduced traceback, likely `client.py`, `receiver.py`, `media.py`, or lifecycle code in `__init__.py`.

**Interfaces:**
- `assert-clean-ha-log.py PATH` fails on unhandled `aiohttp.server` request tracebacks or unhandled Matrix Extended background-task exceptions while allowing explicitly asserted expected warnings.

- [ ] **Step 1: Capture the exact failing request/operation from the real stack**

Run the 0.4.1 baseline unchanged and reproduce the local-client operations corresponding to the prior `aiohttp.server` errors. Preserve the complete traceback in the CI job log, with secrets redacted.

- [ ] **Step 2: Add failing regression test before changing runtime code**

Encode the exact request/event/reconnect sequence in `test_resilience.py`. The test must fail on imported 0.4.1 for the same reason as the observed traceback.

- [ ] **Step 3: Apply the smallest runtime fix**

Change only the failing lifecycle/request boundary. Do not broadly catch `Exception` around unrelated logic and do not suppress tracebacks without returning a correct HA/Matrix result.

- [ ] **Step 4: Exercise outage/reconnect/reload/restart**

Cover:
- Synapse stop during sync;
- Synapse restart and recovery;
- repeated integration reload;
- Home Assistant restart with the config entry/store preserved;
- invalid token/config-entry auth failure;
- no leaked listener/background tasks after unload.

- [ ] **Step 5: Scan logs**

Run:

```bash
python ci/scripts/assert-clean-ha-log.py .ci/home-assistant.log
```

Expected: no unhandled `aiohttp.server` tracebacks and no `Task exception was never retrieved` for Matrix Extended.

- [ ] **Step 6: Commit regression fix**

```bash
git add tests/e2e/test_resilience.py ci/scripts/assert-clean-ha-log.py custom_components/matrix_extended
git commit -m "fix: harden Matrix Extended request and reconnect lifecycle"
```

---

### Task 8: Failure artifacts, final verification and merge gate

**Files:**
- Modify: `.github/workflows/test.yml`
- Modify: `README.md`
- Create: `docs/TESTING.md`

**Interfaces:**
- CI uploads sanitized diagnostic bundle only on failure.

- [ ] **Step 1: Add failure artifact collection**

Collect:
- pytest JUnit XML;
- HA log;
- Synapse log;
- Docker/service status;
- sanitized non-secret test configuration.

Before upload, redact values matching access-token/password/auth-header fields.

- [ ] **Step 2: Document developer workflow**

`docs/TESTING.md` documents:

```text
fast: validate-source + compileall + pytest
real stack: Synapse 1.160.0 + HA 2026.9.2 + tests/e2e
release rule: both gates green before merge/tag/package
```

- [ ] **Step 3: Run complete verification**

```bash
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
# In Docker-capable CI:
docker compose -f compose.test.yml up -d synapse
python ci/scripts/bootstrap-matrix.py
pytest -q tests/e2e --junitxml=.ci/e2e.xml
```

Expected: zero failures.

- [ ] **Step 4: Verify install package content**

Build the HA install ZIP from `custom_components/matrix_extended`, extract it, compile it, and compare the packaged component file list/content with the repository component tree. No cache/test/source-only files may enter the install ZIP.

- [ ] **Step 5: Open PR only after both gates are green**

The PR body records:
- baseline 0.4.1 and 129/129 imported tests;
- HA 2026.9.2 / Synapse 1.160.0 E2E result;
- reproduced/fixed `aiohttp.server` regression status;
- artifact/package verification.
