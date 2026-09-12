# Testing Matrix Extended

Matrix Extended uses two mandatory CI gates before merge or release.

## Fast regression gate

The fast job runs on Python 3.13 and performs:

```bash
python -m pip install -r requirements-test.txt
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

The current v0.4.2 branch has 147 regression tests. This suite includes the imported v0.4.1 behavior tests plus regressions for source validation, Synapse readiness, config-flow schema compatibility, E2EE runtime dependencies, Matrix disconnect status, reconnect container handling, and Home Assistant event-loop blocking.

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

Do not merge, tag, or publish an install archive unless both the fast regression gate and the real HA + Synapse gate are green on the release commit.

Never upload `.ci/matrix-env.json`, `.ci/matrix-passwords.json`, Synapse registration secrets, Matrix access tokens, passwords, crypto-store keys, or Authorization headers as CI artifacts.
