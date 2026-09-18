# Native Matrix control panels

**English** · [Русский](CONTROL_PANELS.ru.md)

Native Matrix Control is the `0.6.0b1` control surface for Matrix Extended. It turns one ordinary Matrix room into a live Home Assistant status/control message without giving Matrix clients a Home Assistant token.

## Scope in 0.6.0b1

- A panel uses an **existing Matrix room**. This beta does not create rooms or Spaces.
- Exactly **one panel per room** is supported.
- The panel has one stable root `m.room.message`. State changes update that same logical message with `m.replace`; Matrix Extended does not create a new root for every state change.
- Controls are Matrix reactions attached to the root. Matrix carries only the configured reaction/action reference; the Home Assistant service, target and data stay stored locally in Home Assistant.
- The future Matrix Extended **Widget** is planned for a later beta and is not included in `0.6.0b1`.

## Security model

Control panels reuse Matrix Extended's fail-closed account policy. The room must be inside the account `allowed_rooms`, and the sender must already be inside the account `allowed_users`. A panel-level `allowed_users` list can only narrow that account allowlist; it cannot grant access to another Matrix user.

Actions are predefined. A Matrix user cannot submit an arbitrary Home Assistant service, target, YAML, Jinja template or service-data object through a reaction. The configured action ID resolves locally to the stored safe action.

With matrix-nio 0.26.0, an `m.reaction` event itself is not E2EE. Matrix Extended therefore does not treat reaction encryption as the authorization boundary: it validates the authenticated Matrix sender, room, panel root/generation and configured action before execution. Matrix room power levels are an additional Matrix-side control, not a replacement for the integration allowlists.

## Create a panel in the Home Assistant UI

Open **Settings → Devices & services → Matrix Extended → Configure → Native Matrix control panels → Add panel**.

Choose:

- **Panel ID** — stable local identifier such as `garage`.
- **Matrix room** — an existing resolved room ID from the account allowlist.
- **Panel title** — text rendered at the top of the control message.
- **Displayed entities** — Home Assistant entities whose actual state is rendered.
- **Users allowed to control this panel** — optional additional restriction; leave empty to use every account-authorized sender.
- **State update debounce** — rapid Home Assistant state changes are coalesced. Default is 1.5 seconds; accepted range is 0.25–10 seconds.

After creating the draft, add actions. Each action has a stable ID, unique reaction, label, Home Assistant service, target, optional YAML service data, and `confirmation_required`.

The UI uses native Home Assistant service and target selectors. Advanced service data is entered as YAML and must parse to a mapping.

## Normal and dangerous actions

A normal action executes after one authorized reaction on the panel root.

Set `confirmation_required: true` for risky operations such as unlocking a lock, opening a garage/gate, disarming an alarm, or disabling a critical automation. Matrix Extended then creates a confirmation reply and waits up to **30-second** for `✅` or `❌` from the **same sender** that requested the action. A confirmation is bound to the panel/action generation and is single-use. A Home Assistant reload/restart invalidates pending confirmations rather than executing them later.

The visible panel state is driven by the actual Home Assistant entity state after the service call; service-call success by itself is not treated as proof that the device changed.

## Pinning and Matrix permissions

Matrix Extended attempts to add the stable root event to `m.room.pinned_events` while preserving unrelated pins already in the room. The Matrix account must have sufficient room power level to modify pinned events.

A pin failure is non-fatal: the integration and panel can remain operational, while panel diagnostics expose the pin error. Matrix Extended does not continuously hammer the room with re-pin attempts; creation, startup recovery and explicit repair are the relevant lifecycle points.

## Live updates, debounce and Matrix outage behavior

Only the entities selected for the panel are tracked. Updates are event-driven from Home Assistant state changes; there is no polling loop. The configured `debounce` coalesces chatty state transitions and a render hash prevents an `m.replace` when the rendered output is unchanged.

During a temporary Matrix outage, panel state edits are not appended to the normal persistent message outbox one by one. The manager retains/coalesces the latest desired render and retries that state after connectivity returns, avoiding an obsolete edit storm.

## Deleted or redacted root: `needs_repair`

If the known panel root is missing or redacted, Matrix Extended marks the runtime as `needs_repair`. It deliberately does **not** auto-create replacement roots, because that could produce a message storm when a room or permissions are misconfigured.

Use **Configure → Native Matrix control panels → Repair panel message**. Repair creates exactly one new root for that panel, binds controls to the new generation and attempts to pin it. The panel configuration itself is unchanged.

## Diagnostics

The integration exposes a disabled-by-default **Control panels** diagnostic sensor. Its state is the number of active panels. Attributes contain bounded per-panel snapshots such as panel ID, room ID, root event ID, runtime state, pin status, watched entities, action IDs, update timestamps/errors and pending-confirmation count. Service data, access tokens and other secrets are intentionally omitted.

## YAML import/export

The GUI supports export and import of one validated panel as YAML. Import is checked against the current account room/user allowlists, and replacing an existing panel requires explicit confirmation.

Example:

```yaml
panel_id: garage
room_id: "!garage:example.org"
title: Garage
enabled: true
entities:
  - entity_id: cover.garage
    label: Garage door
  - entity_id: light.garage
    label: Garage light
actions:
  - id: light_toggle
    reaction: "💡"
    label: Toggle light
    service: light.toggle
    target:
      entity_id: light.garage
    data: {}
    confirmation_required: false
  - id: garage_open
    reaction: "🔓"
    label: Open garage
    service: cover.open_cover
    target:
      entity_id: cover.garage
    data: {}
    confirmation_required: true
allowed_users:
  - "@owner:example.org"
debounce: 1.5
```

`room_id` must be a resolved `!room:server` ID that belongs to the account `allowed_rooms`. Each reaction and action ID must be unique within the panel.

See [Practical examples](EXAMPLES.md) for garage, alarm and light/climate patterns.