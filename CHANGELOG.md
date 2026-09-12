# Changelog

## 0.4.2 — 2026-09-12

Reliability release validated against real Home Assistant 2026.9.2 and Synapse 1.160.0.

- Fix E2EE installation in Home Assistant environments where the built-in Matrix integration already satisfies the base `matrix-nio==0.26.0` requirement. The required E2EE runtime dependencies are now declared explicitly.
- Fix connection diagnostics during a homeserver outage by bounding matrix-nio transport retries so Matrix Extended can report the disconnect and run its own reconnect loop.
- Verify automatic inbound and encrypted outbound recovery after Synapse restart without reloading Home Assistant.
- Move matrix-nio crypto-store `restore_login()` file access out of Home Assistant's event loop.
- Add real-stack CI covering config flow, encrypted send, reload, Synapse outage/recovery, inbound recovery, Home Assistant restart, and runtime log safety.
- Add a fast source/compile/regression gate; current release branch has 149 passing tests.
- Add a verified release-package gate that creates the Home Assistant install ZIP only after both mandatory test gates succeed, checks its contents byte-for-byte against the component tree, and publishes the archive with a SHA-256 checksum.

## 0.4.1

Baseline imported from the previously built Home Assistant install/source artifacts and preserved as the behavior reference for this release line.
