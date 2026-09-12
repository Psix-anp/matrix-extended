# Testing Matrix Extended

Matrix Extended uses two mandatory test gates before merge or release, followed by a release-package gate that only runs when both test gates are green.

## Fast regression gate

The fast job runs on Python 3.13 and performs:

```bash
python -m pip install -r requirements-test.txt
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

The current v0.4.2 branch has 149 regression tests. This suite includes the imported v0.4.1 behavior tests plus regressions for source validation, release-archive integrity, Synapse readiness, config-flow schema compatibility, E2EE runtime dependencies, Matrix disconnect status, reconnect container handling, and Home Assistant event-loop blocking.

## Real Home Assistant + Synapse gate

The real-stack job runs disposable containers pinned to:

- Home Assistant `2026.9.2`
- Synapse `1.160.0`

It bootstraps two temporary Matrix users and an encrypted room, then verifies the actual integration through Home Assistant's APIs rather than writing config-entry storage by hand.

The job checks:

1. Home Assistant onboarding and Matrix Extended config flow.
2. Config entry reaches `loaded`.
3. A real encrypted Matrix event is sent through Synapse.
4. Integration reload succeeds.
5. Synapse is stopped while Home Assistant remains running and the connection entity changes to `off`.
6. Synapse is started again and the existing Matrix listener recovers without a Home Assistant reload.
7. A second Matrix user sends an inbound event and Home Assistant receives it after recovery.
8. Encrypted outbound sending works again after recovery.
9. Home Assistant is restarted and the persisted config entry returns to `loaded`.
10. Home Assistant logs contain no Matrix Extended event-loop blocking warning or leaked unhandled background-task exception.

## Verified release package

The package job depends on both mandatory test jobs. It runs only after they succeed and executes:

```bash
python ci/scripts/build-release.py
```

The builder reads the version from `custom_components/matrix_extended/manifest.json`, creates `dist/matrix_extended-ha-install-v<version>.zip`, and then reopens the archive and compares every file byte-for-byte with the source component tree. Generated caches and bytecode are excluded, and any file outside `custom_components/matrix_extended/` makes verification fail.

GitHub Actions publishes the verified install ZIP together with its SHA-256 checksum as a workflow artifact. Matrix credentials, access tokens, passwords, Synapse secrets, crypto-store data, and Home Assistant runtime configuration are never included in that artifact.

## Local real-stack run

On a Docker-capable machine:

```bash
ci/scripts/prepare-synapse.sh
E2E_UID="$(id -u)" E2E_GID="$(id -g)" docker compose -f compose.test.yml up -d synapse
python ci/scripts/wait-http.py http://127.0.0.1:8008/_matrix/client/versions 90
MATRIX_REGISTRATION_SHARED_SECRET="$(cat .ci/synapse-shared-secret)" python ci/scripts/bootstrap-matrix.py
ci/scripts/prepare-ha.sh
docker compose -f compose.test.yml up -d homeassistant
python ci/scripts/wait-http.py http://127.0.0.1:8123/api/onboarding 180
python ci/scripts/ha-e2e.py setup-send-reload
```

The CI workflow additionally executes the outage/reconnect and Home Assistant restart scenarios.

## Release rule

Do not merge, tag, or publish an install archive unless both the fast regression gate and the real HA + Synapse gate are green on the release commit. The install archive must be produced by the verified package job from that same commit.

Never upload `.ci/matrix-env.json`, `.ci/matrix-passwords.json`, Synapse registration secrets, Matrix access tokens, passwords, crypto-store keys, or Authorization headers as CI artifacts.
