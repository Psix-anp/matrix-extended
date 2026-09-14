# Matrix Extended settings

Matrix Extended is designed to be configured from the Home Assistant UI. YAML is not required for integration setup.

Open **Settings → Devices & services → Matrix Extended → Configure**. The options flow is split into four sections.

## General

- **Default room** — Matrix room ID (`!...`) or alias (`#...`). Used when an action does not specify `Rooms` or `Route`.
- **Verify TLS certificate** — keep enabled for normal HTTPS homeservers. Disable only for a deliberately trusted local/test deployment.
- **Require E2EE** — when enabled, Matrix Extended refuses outbound delivery to plaintext target rooms.

Changing the default room or TLS setting reloads the config entry so the runtime connection uses the new value.

## Incoming & security

- **Enable incoming events** — starts Matrix inbound processing.
- **Allowed users** — Matrix sender IDs allowed to reach Home Assistant.
- **Allowed rooms** — Matrix rooms allowed to reach Home Assistant.

Incoming processing is fail-closed: when incoming events are enabled, both allowlists must be non-empty and both the sender and room must match. Own transaction echoes are ignored.

Use dedicated Matrix accounts/rooms for automations that can trigger sensitive Home Assistant actions.

## Incoming media

- **Download and decrypt incoming media** — store incoming Matrix attachments locally for automations.
- **Retention, days** — age-based cleanup. `0` disables age cleanup.
- **Storage limit, MiB** — upper bound for the integration-owned incoming-media directory.

Files are stored below:

```text
/config/matrix_extended/incoming/<config_entry_id>/
```

`matrix_extended.purge_media` can perform an immediate manual cleanup.

## Notification routes

Routes are reusable names for one or more Matrix rooms. They are managed graphically with **Add route**, **Edit route**, and **Delete route**.

Example route:

```text
security → !garage:example.org, !gate:example.org
```

An automation can then use `route: security` instead of hard-coding both room IDs. `route` and explicit `target`/Rooms are mutually exclusive.

## Default-room select entity

Matrix Extended also exposes a **Default room** select entity using joined-room labels. Changing it persists the selected room and updates the integration default.

## Diagnostics

The integration device exposes:

- connection state;
- Matrix user/device IDs;
- default room and its encryption state;
- last successful send;
- last incoming event with event-specific attributes;
- last error (`No errors` when clear).

## Persistent data

E2EE crypto state and integration registries are kept under Home Assistant storage. Do not manually edit these files while Home Assistant is running.

```text
/config/.storage/matrix_extended/<config_entry_id>/
```

For action fields and automation behavior, see [ACTIONS.md](ACTIONS.md). For ready-to-copy YAML, see [EXAMPLES.md](EXAMPLES.md).
