# Testing Matrix Extended

Matrix Extended 0.5.0 uses three mandatory release gates.

## 1. Fast regression gate

Runs on Python 3.13:

```bash
python -m pip install -r requirements-test.txt
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

Current release branch: **231 regression tests**.

Coverage includes source/package validation, config flow, E2EE dependencies, rich content, mentions/Markdown, reaction-action persistence and limits, delivery responses/events, incoming edits/redactions/location/media retention, voice/STT safety, persistent outbox, Element E2E harness contracts and release metadata.

## 2. Real Home Assistant + Synapse + Element gate

Disposable stack is pinned to:

- Home Assistant `2026.9.2`
- Synapse `1.160.0`
- Element Web `1.12.26`

The gate creates temporary Matrix users and an encrypted room, logs a real Element recipient in before Home Assistant sends encrypted data, then verifies:

1. Home Assistant onboarding and Matrix Extended config flow.
2. Config entry reaches `loaded` and survives reload.
3. Real encrypted text is sent through Synapse and decrypted in Element.
4. Encrypted `m.location` renders as Element's native location map.
5. Native Matrix voice renders in Element's voice player.
6. Synapse is stopped while Home Assistant remains online and the integration reports the outage.
7. A send while offline returns `queued` immediately and persists in the outbox.
8. Synapse restart drains the queued message automatically.
9. Inbound listener and encrypted outbound sending recover without a Home Assistant reload.
10. Home Assistant restart restores the persisted config entry and one-shot reaction-action state.
11. Runtime logs contain no Matrix Extended event-loop blocking warning or leaked background-task exception.
12. Real Element screenshots are uploaded as CI artifacts.

The Element showcase uses neutral Amsterdam coordinates (`52.3676, 4.9041`) and a public OpenFreeMap style. The map provider is CI-only; Matrix Extended itself only sends standard Matrix location events.

## 3. Verified install ZIP

Runs only after both test gates are green:

```bash
python ci/scripts/build-release.py
```

The builder reads the version from `custom_components/matrix_extended/manifest.json`, creates `dist/matrix_extended-ha-install-v<version>.zip`, reopens it, and compares every archive file byte-for-byte with the component tree. A SHA-256 checksum is emitted with the artifact.

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
```

CI additionally runs the browser E2E, rich location/voice validation, outage/outbox/recovery scenario and Home Assistant restart.

## Release rule

Do not merge, tag or publish a release package unless fast regression, real-stack and verified-package jobs are green on the exact release commit.
