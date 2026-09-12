# Matrix Extended test harness design

## Goal

Matrix Extended must not publish or merge behavior changes before they pass reproducible tests against both Home Assistant and a real Matrix Synapse server. Fast unit/regression checks run first; end-to-end checks run against a disposable HA + Synapse stack in CI before merge.

## Constraints

- The repository currently contains only a minimal README, so the test harness must be established before the integration starts accumulating untested code.
- The current ChatGPT execution environment has Python 3.13.5 but no Docker or Podman. Therefore it can run source-level checks that need only the available Python environment, while the real multi-service stack runs in GitHub Actions where Docker is available.
- No manual user-side validation is required for routine changes. CI must reproduce failures and preserve useful logs/artifacts.
- The project should remain small and maintainable. Do not add extra orchestration layers when Docker Compose plus test scripts are sufficient.

## Repository layout

```text
custom_components/matrix_extended/
  __init__.py
  manifest.json
  config_flow.py
  const.py
  ... integration modules ...

tests/
  unit/
  regression/
  e2e/
    conftest.py
    test_setup.py
    test_messaging.py
    test_reconnect.py
    test_failures.py

ci/
  synapse/
    homeserver.yaml
  homeassistant/
    configuration.yaml
  scripts/
    wait-for-synapse.sh
    wait-for-ha.sh
    bootstrap-matrix.sh
    run-e2e.sh

compose.test.yml
.github/workflows/test.yml
```

The exact integration modules may grow as features are restored, but tests and CI remain separated by responsibility.

## Test levels

### 1. Static and unit checks

Purpose: fail quickly without external services.

Covers:
- Python syntax/import validation;
- manifest and translation structure;
- pure Matrix payload parsing/serialization;
- URL and credential validation helpers;
- state conversion helpers;
- service/action argument validation;
- known regression cases that do not require a running HA core.

These checks run on every push and pull request.

### 2. Home Assistant integration tests

Purpose: validate integration lifecycle and Home Assistant API behavior.

Covers:
- config flow success and authentication errors;
- config entry setup/unload/reload;
- entity/service registration;
- repeated setup without duplicate listeners/routes;
- unload cleanup;
- exception handling that must not leak unhandled `aiohttp.server` tracebacks;
- migration behavior when integration schema changes.

Where possible, network boundaries are controlled deterministically. These tests are not a replacement for the E2E stack.

### 3. Real HA + Synapse E2E

Purpose: prove the integration works with actual service processes rather than mocks.

The workflow starts:
- Home Assistant Container;
- Matrix Synapse;
- a disposable test network;
- Matrix test users and at least one room.

The bootstrap script waits for service health, creates users, authenticates them, creates/joins a room, and exposes only ephemeral CI credentials.

E2E scenarios cover at minimum:
- integration setup against Synapse;
- successful authentication;
- send a text event through the integration and verify it via Matrix API;
- receive/observe a Matrix event where the integration supports inbound handling;
- media send path when implemented;
- invalid token and invalid homeserver URL;
- Synapse temporarily unavailable;
- Synapse restart followed by reconnect/recovery;
- Home Assistant restart with the config entry preserved;
- integration reload/unload without stale background tasks;
- repeated client requests that previously produced `aiohttp.server` errors;
- absence of unhandled exceptions in Home Assistant logs for the tested scenarios.

## Regression policy

Every confirmed bug gets a regression test before or together with the fix. A fix is incomplete if the original failure cannot be reproduced by a test or a deterministic E2E scenario.

For the known `aiohttp.server` failure class, the harness must capture the offending request shape once the implementation is restored, assert the correct HTTP/result behavior, and scan HA logs to ensure the request does not produce an unhandled traceback.

## CI workflow

The main workflow has two gates.

### Fast gate

Runs lint/static/unit/regression checks. Failure stops the workflow before the E2E stack is started.

### E2E gate

Builds/starts the test stack with Docker Compose, bootstraps Synapse, installs the checked-out custom integration into the Home Assistant config volume, starts HA, and runs the E2E test suite.

On failure, the workflow uploads:
- Home Assistant log;
- Synapse log;
- pytest/JUnit result;
- service status output;
- relevant sanitized configuration.

Secrets, access tokens, passwords, cookies, and authorization headers must be redacted from artifacts.

## Branch and publication policy

- Development happens in a feature branch, not directly in `main`.
- Pull requests require the fast gate and E2E gate to pass before merge.
- A release/tag/package is cut only from a commit that passed both gates.
- Failed tests are fixed in the branch; they are not bypassed to publish a build.

## Local execution in the current environment

Because Docker/Podman are not installed in the current ChatGPT runtime, the same repository still exposes commands for the fast test gate locally. Full-stack validation is delegated to the GitHub Actions runner before merge.

If a future execution environment provides Docker, `docker compose -f compose.test.yml up --abort-on-container-exit` (or the repository wrapper script) should reproduce the same E2E stack locally without changing test semantics.

## Failure handling

- Service readiness uses explicit health polling with bounded timeouts.
- Synapse/HA startup failures produce logs before CI exits.
- Matrix bootstrap calls fail loudly and print sanitized response metadata.
- Test retries are not used to hide deterministic failures. A retry is allowed only for a narrowly documented transient operation and must preserve the first failure in diagnostics.
- Integration background tasks must be cancelled and awaited during unload/reload.

## Acceptance criteria

The harness is considered established when:

1. The repository contains the integration test layout and a runnable CI workflow.
2. The workflow starts real Home Assistant and Synapse services.
3. CI creates disposable Matrix credentials and a room automatically.
4. At least one end-to-end message path is verified through the real Matrix API.
5. Integration setup, unload/reload, Synapse outage/reconnect, and HA restart are tested.
6. HA and Synapse logs are captured on failure and sanitized.
7. The known `aiohttp.server` failure class has a reproducible regression test once the restored integration code identifies the exact route/request.
8. Pull requests are not considered ready until both the fast and E2E gates are green.

## Scope boundary

This work establishes the development and verification infrastructure. It does not redesign Matrix Extended features. Existing feature behavior will be restored into the repository and then evolved separately, with each change required to use this test path.
