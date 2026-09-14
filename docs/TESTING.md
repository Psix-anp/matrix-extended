# Testing Matrix Extended

**English** · [Русский](TESTING.ru.md)

Matrix Extended uses mandatory release gates. A release is not merged or packaged from an unverified commit.

## 1. Fast regression gate

Runs on Python 3.13:

```bash
python -m pip install -r requirements-test.txt
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

Coverage includes config/setup flows, selector contracts, E2EE dependencies, rich content, media resolution, mentions/Markdown, reaction-action persistence and limits, delivery responses/events, incoming events and retention, voice/STT safety, notify entities, persistent outbox, Element E2E harness contracts and release packaging.

Test counts are intentionally not hard-coded in this document; CI output is the source of truth.

## 2. Clean manifest runtime gate

Runs with Python 3.14 in a fresh virtual environment and installs only dependencies declared by the integration manifest. It then instantiates matrix-nio with encryption enabled.

This protects against a test environment accidentally hiding missing runtime/E2EE dependencies.

## 3. Real Home Assistant + Synapse + Element gate

Disposable stack is pinned to:

- Home Assistant `2026.9.2`
- Synapse `1.160.0`
- Element Web `1.12.26`

The gate creates temporary Matrix users and an encrypted room, logs a real Element recipient in before Home Assistant sends encrypted data, then verifies:

1. Home Assistant starts and accepts Matrix Extended service metadata with the real Home Assistant parser.
2. Matrix Extended config entry loads and survives reload.
3. Real encrypted text is sent through Synapse and decrypted in Element.
4. Default and room-specific Matrix notify entities are registered in Home Assistant.
5. Rich Matrix events render in Element.
6. The graphical `matrix_extended.send_media` action executes through real Home Assistant Media Source handling.
7. Synapse is stopped while Home Assistant remains running and the integration reports the outage.
8. A send while offline is persisted in the outbox.
9. Synapse restart drains the queued message and inbound/outbound traffic recovers without an HA reload.
10. Home Assistant restart restores the config entry and persisted integration state.
11. A real Matrix reaction updates the rich **Last incoming event** diagnostic.
12. Runtime logs contain no Matrix Extended event-loop blocking warning or leaked background-task exception.
13. Real Element screenshots are uploaded as CI artifacts.

The Element showcase uses neutral test coordinates and a public map style. The map provider is CI-only; Matrix Extended itself sends standard Matrix location events.

## 4. Verified install ZIP

Runs only after the preceding gates are green:

```bash
python ci/scripts/build-release.py
```

The builder reads the version from `custom_components/matrix_extended/manifest.json`, creates `dist/matrix_extended-ha-install-v<version>.zip`, reopens it, and compares every archive file byte-for-byte with the component tree. CI also creates a SHA-256 checksum.

Secrets, passwords, access tokens, Synapse registration secrets, crypto stores and Home Assistant runtime config are never included.

## Local real-stack smoke test

On a Docker-capable machine:

```bash
ci/scripts/prepare-synapse.sh
E2E_UID="$(id -u)" E2E_GID="$(id -g)" docker compose -f compose.test.yml up -d synapse
python ci/scripts/wait-http.py http://127.0.0.1:8008/_matrix/client/versions 90
MATRIX_REGISTRATION_SHARED_SECRET="$(cat .ci/synapse-shared-secret)" python ci/scripts/bootstrap-matrix.py
ci/scripts/prepare-ha.sh
docker compose -f compose.test.yml up -d --no-deps element
docker compose -f compose.test.yml up -d homeassistant
python ci/scripts/wait-http.py http://127.0.0.1:8123/api/onboarding 180
python ci/scripts/ha-e2e.py setup-send-reload
python ci/scripts/verify-ha-entities.py
python ci/scripts/verify-runtime.py send-media
```

CI additionally runs browser E2E, outage/outbox/recovery, Home Assistant restart, incoming-event diagnostics and the install-package gate.

## Release rule

Do not merge, tag or publish a release package unless fast regression, clean manifest runtime, real-stack and verified-package jobs are green on the exact release commit.
