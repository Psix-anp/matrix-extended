# Matrix Native Control Design for 0.6.0b1

## Status

Approved design for the first Matrix Extended 0.6 beta. This document defines the architecture, security model, configuration, runtime behavior, recovery behavior, testing requirements, and the compatibility boundary for the later Matrix Widget work.

## Goal

Add safe, persistent Home Assistant control surfaces to existing Matrix rooms without requiring a custom Matrix client or a Widget. A room gets one maintained control message that shows selected HA states and exposes predefined actions through Matrix reactions. The same backend action model must later serve a graphical Matrix Widget without creating a second authorization or execution system.

## Scope

0.6.0b1 includes:

- existing Matrix rooms only;
- one control panel root message per configured room;
- explicitly configured Home Assistant entities;
- explicitly configured actions;
- reaction-driven control in ordinary Element/Matrix clients;
- a shared Safe Action Engine for text commands, reaction actions, and control-panel actions;
- two-step confirmation for dangerous actions;
- event-driven HA state updates with debounce and `m.replace` edits;
- optional pinning through `m.room.pinned_events`;
- threads for incident/event follow-up;
- persistent runtime metadata and repair behavior;
- Options Flow configuration and YAML import/export of panel definitions;
- diagnostics and real-stack regression coverage.

0.6.0b1 does not include:

- automatic Space or room creation;
- a Matrix Widget;
- automatic import of all HA entities;
- arbitrary Jinja rendering;
- free-form service execution from Matrix event payloads;
- complex action conditions;
- direct HA API access from Matrix clients;
- cross-signing or new sync protocol work;
- timeline/history scanning to rediscover a lost panel root.

Automatic Space/room setup is deferred to a later beta. The graphical Matrix Widget is deferred to 0.6.0b2.

## Architectural Decision

Use one Safe Action Engine as the execution boundary. Text commands, existing reaction actions, native control-panel reactions, and the future Widget are input adapters only. They normalize user intent into a validated internal action reference. The engine executes only actions already stored inside Matrix Extended.

No Matrix event may carry an arbitrary `domain.service` payload that is executed directly. Matrix events identify a predefined action, for example `garage.open`; the actual HA service, target, and data are stored by the integration.

This reuses the existing security approach instead of introducing a second control stack.

## Security Model

Authorization is fail-closed.

The account-level `allowed_users` and `allowed_rooms` remain the outer security boundary. A panel may further restrict users, but it may never broaden the account policy.

For a control action to execute, all of the following must still be true at execution time:

1. the Matrix room is allowed by the account policy;
2. the Matrix sender is allowed by the account policy;
3. the panel belongs to that room;
4. the reaction/event targets the current panel root event;
5. the action exists in the current panel configuration;
6. the panel-level user restriction, when configured, permits the sender;
7. the action has not been invalidated or replaced;
8. any required confirmation is valid and unexpired.

Dangerous actions use a two-step confirmation flow. Typical dangerous actions include unlock, disarm, opening a garage/gate, and disabling critical automation.

Confirmation rules:

- expiry: 30 seconds;
- only the same Matrix sender may confirm;
- confirmation is bound to `panel_id`, `action_id`, sender, and the active panel generation/root;
- `✅` confirms and `❌` cancels;
- timeout cancels;
- another sender cannot consume the confirmation;
- changing/replacing the source panel/action invalidates stale confirmation state;
- confirmation stores an action reference, not a copied arbitrary service payload;
- pending confirmations are intentionally dropped on Home Assistant restart/reload.

Ordinary low-risk actions such as lights, climate, and media execute without a second confirmation.

## Control Panel Model

Each configured panel belongs to one Matrix account and one existing Matrix room.

Logical model:

```yaml
panel_id: garage
room: "!room:example.org"
title: "🏠 Garage"
enabled: true
entities:
  - entity_id: cover.garage
    label: "Gate"
  - entity_id: light.garage
    label: "Light"
  - entity_id: sensor.garage_temperature
    label: "Temperature"
actions:
  - id: garage_open
    reaction: "🔼"
    label: "Open"
    service: cover.open_cover
    target:
      entity_id: cover.garage
    data: {}
    confirmation_required: true
allowed_users:
  - "@sergey:example.org"
debounce: 1.5
```

Rules:

- `panel_id` is unique within one Matrix account;
- there is at most one control panel per Matrix room in 0.6.0b1;
- action IDs are unique within the panel;
- reaction keys are unique within the panel;
- configured entities are the only HA entities subscribed by that panel;
- unsupported entity domains fall back to the raw HA state;
- 0.6.0b1 does not execute Jinja/templates while rendering panels.

The GUI is the source of truth. YAML is an import/export format for panel definitions, not a second live configuration source.

## Matrix Representation

The panel root is an ordinary `m.room.message` so every Matrix client has a useful fallback. It includes human-readable `body`, optional formatted HTML, and a namespaced marker:

```json
{
  "msgtype": "m.text",
  "body": "🏠 Garage\n\n🚪 Gate: Closed\n💡 Light: On\n🌡 Temperature: 18.7 °C\n\n🔼 Open  🔽 Close  💡 Light  📷 Camera",
  "io.psix.matrix_extended.panel": {
    "schema": 1,
    "panel_id": "garage"
  }
}
```

The original root `event_id` is stable for the lifetime of that panel root. State refreshes are sent as `m.replace` edits targeting the original root. A state update does not create a new root message.

The integration adds reaction options for the configured actions. The text body includes a readable legend so clients that only render normal Matrix content remain understandable.

The current action registry model is extended/reused so reaction handling is bound to room, root event, reaction, sender policy, expiry/usage semantics, and panel/action references.

## Pinning

Matrix Extended attempts to add the panel root event to `m.room.pinned_events` without deleting unrelated existing pins.

Pinning is optional enhancement, not a requirement for control. If the Matrix account lacks sufficient power level to update room state:

- the panel remains active;
- reactions remain usable;
- diagnostics show a non-fatal `not pinned / insufficient power level` condition.

If a user manually removes the pin, Matrix Extended does not continuously fight that choice. Automatic pinning is attempted only when a new panel root is created. An explicit repair action may pin the repaired/new root again. Ordinary startup does not re-pin an existing root that is currently unpinned.

## Home Assistant State Flow

Home Assistant is always the source of truth for displayed state.

Each active panel subscribes only to the HA entities present in that panel. No polling loop is used.

State flow:

`HA state event -> panel dirty -> debounce -> render -> render hash compare -> m.replace when changed`

Default debounce is 1.5 seconds. Multiple state changes inside the debounce window collapse into one render/edit.

After an action call succeeds, the panel does not optimistically invent a final HA state. It waits for the actual HA state event. For example, after `cover.open_cover`, the panel may legitimately show `opening` before it shows `open`.

During Matrix/Synapse outage, the panel manager retains only the latest desired rendered state. It must not enqueue an edit for every intermediate HA state. After connectivity recovers, one update brings the Matrix panel to current HA state.

## Safe Action Engine

Introduce a normalized internal action definition that covers the common execution requirements currently split across command and reaction paths.

The engine consumes a validated action definition containing:

- stable action ID;
- handler type;
- service / target / data for service handlers, or another explicitly supported bounded handler;
- security metadata supplied by the caller/context;
- whether confirmation is required.

The engine is responsible for execution, bounded/redacted error reporting, and a normalized result. It does not decide Matrix authorization on its own; authorization remains in the input/control layer and is revalidated before execution.

Existing safe text commands and reaction actions should migrate to/reuse this execution core rather than keep independent service-call implementations.

## Incident Threads

Control panels are for current control/status. Incidents are separate root events.

Examples include alarm triggers, camera detections, system failures, and noteworthy automation events. Follow-up material such as snapshots, clips, operator comments, acknowledgement, and resolution belongs in the thread rooted at that incident event.

Read receipts mean seen/displayed, not acknowledged. Explicit acknowledgement remains an intentional action such as a `✅` reaction or another registered action.

## Configuration UX

Add `Control panels` to the existing Matrix Extended Options Flow.

Expected flow:

`Control panels -> Add/Edit panel -> Room -> Entities -> Actions -> Security -> Save`

The room selector uses rooms already available to the configured Matrix account. The integration does not create rooms in 0.6.0b1.

Entity selection uses Home Assistant entity selectors. Action configuration collects:

- action ID;
- label;
- reaction key;
- service;
- target;
- data;
- `confirmation_required`.

Security configuration collects any panel-level user restriction. Validation must reject a panel that attempts to rely on users/rooms outside the account-level allowlists.

Provide panel definition export and import as YAML. Imported YAML is validated and then stored as normal Options Flow configuration.

## Runtime Persistence

Panel configuration is stored in `config_entry.options`.

Runtime metadata is stored separately in Home Assistant `Store`. Per panel, persist at least:

- `panel_id`;
- resolved `room_id`;
- current root `event_id`;
- last successful render hash;
- pin status/last pin error information suitable for diagnostics;
- panel generation/version needed to invalidate stale confirmations.

Pending confirmations are in-memory only and are dropped on HA restart/reload. This is a deliberate safety property: restart can only cancel an unconfirmed dangerous action, never advance it toward execution.

## Startup and Recovery

On setup/reload/restart:

1. load configuration and runtime store;
2. connect/sync the Matrix account;
3. resolve the configured existing room;
4. restore the known root event ID from runtime state;
5. subscribe to the configured HA entities;
6. render current HA state;
7. update the existing root only when the render differs;
8. report current pin state without automatically re-pinning an existing root.

No duplicate control root should be created during ordinary HA restart.

If editing the stored root proves that it was redacted/deleted or is otherwise unusable, the panel enters `needs_repair`. Matrix Extended does not automatically create repeated roots in a retry loop. An explicit repair operation creates exactly one new root, registers actions against the new root, persists the new event ID, and attempts to pin the new root.

If the runtime Store is lost or the panel has no stored root event ID, 0.6.0b1 does not scan Matrix history to guess the old root. The panel enters `needs_repair`; explicit repair creates one new root and records it. Human-readable message text is never used to identify an old panel root.

## Error Handling and Diagnostics

Action execution failures produce a bounded user-visible failure result/reply and diagnostics. Error strings must use the existing secret-redaction policy and must not expose access tokens, passwords, auth signatures, or other obvious credentials.

A service call success is distinct from the resulting HA entity state. The panel reflects the latter only after real state feedback.

Diagnostics should expose, per panel:

- enabled/disabled;
- room ID;
- root event ID presence;
- active / needs repair;
- pinned / not pinned and last pin failure category;
- number of watched entities;
- number of actions;
- last successful render/update time;
- last update error category;
- pending confirmation count;
- reconnect/recovery status where relevant.

Missing pin permission is a warning, not a panel setup failure.

## Widget Compatibility Boundary

0.6.0b1 must establish stable machine identities that 0.6.0b2 can reuse:

- `panel_id`;
- `action_id`;
- entity identity plus rendered/display state;
- `confirmation_required`;
- `request_id`, generated uniquely for each action request/result correlation.

Reserve namespaced event families such as:

- `io.psix.matrix_extended.panel`;
- `io.psix.matrix_extended.action`;
- `io.psix.matrix_extended.action_result`.

0.6.0b1 should prefer standard Matrix events (`m.room.message`, `m.reaction`, `m.replace`, `m.room.pinned_events`) when an ordinary Element client can already do the job. The custom event protocol becomes primarily relevant to the Widget.

The future Widget must not hold a Home Assistant access token and must not call HA directly. Its control path is:

`Widget -> Matrix event -> Matrix Extended authorization -> Safe Action Engine -> HA -> Matrix state/result -> Widget`

Ordinary Element reaction control remains:

`Reaction -> Matrix Extended authorization -> same Safe Action Engine -> HA`

Thus the Widget and native reaction UI are two frontends over one control protocol and execution core.

## Testing Strategy

Development is TDD-first for new behavior.

### Unit and Regression Tests

Cover at minimum:

- panel config parsing and validation;
- one panel per room rule;
- action ID and reaction uniqueness;
- account policy cannot be broadened by panel policy;
- normalized Safe Action Engine service execution;
- error redaction;
- dangerous action confirmation success;
- timeout;
- wrong sender;
- cancel;
- stale panel generation/action invalidation;
- replay/duplicate confirmation rejection;
- render output and render hashing;
- debounce collapse;
- common HA domain state rendering and unknown-domain fallback;
- runtime store restore;
- repair state transitions;
- pin list merging without removing foreign pins.

### Integration Tests

Cover at minimum:

- HA state change produces one `m.replace`;
- multiple fast HA changes produce one Matrix edit;
- action invocation calls the expected HA service;
- resulting panel state is based on a real HA state event, not optimistic mutation;
- Matrix outage collapses many HA changes to one final post-recovery update;
- pin permission failure does not disable panel control;
- redacted root leads to `needs_repair` and explicit repair creates one new root without a message storm.

### Security Tests

Cover at minimum:

- unauthorized sender;
- unauthorized room;
- panel user outside account allowlist;
- forged/unknown action ID;
- reaction against an unrelated event;
- stale confirmation;
- confirmation by another user;
- replayed consumed confirmation;
- HA restart/reload drops pending confirmation without executing it.

### Real Stack Gate

Before publishing 0.6.0b1, run the existing real environment using the project baseline versions:

- Home Assistant 2026.9.2;
- Synapse 1.160.0;
- Element Web 1.12.26;
- Python 3.14 runtime with E2EE.

The release candidate must prove the complete path in a real encrypted room:

1. configure a panel for an existing room;
2. create/render the control root through explicit panel setup/repair;
3. pin it when power level allows;
4. change a HA entity and observe an edit in Element;
5. trigger a low-risk reaction action and observe the real HA state update;
6. trigger a dangerous action, require same-user confirmation, and then execute;
7. restart HA and confirm no duplicate root and no pending confirmation survives;
8. interrupt/recover Synapse and confirm state coalescing plus restored control;
9. redact the root and verify `needs_repair`, then repair once and verify exactly one new root;
10. verify no leaked/blocked background tasks;
11. build and verify the install ZIP.

## Release Gate

0.6.0b1 is published only after all current project gates are green:

- fast regression gate;
- clean Python 3.14 + E2EE runtime;
- real HA/Synapse/Element stack;
- verified install ZIP;
- Hassfest/HACS validation as applicable to the release branch/main workflow.

The GitHub release is marked Pre-release and contains bilingual EN/RU notes, exact version/commit, changes/fixes, breaking/migration notes when applicable, test status, install ZIP, and SHA256.

## Success Criteria

0.6.0b1 is successful when an ordinary Element user can safely control explicitly configured HA entities from a maintained Matrix room message, see live HA state reflected without polling or timeline spam, confirm dangerous actions securely, survive HA/Synapse restarts and outages without duplicated control roots, recover explicitly from a missing/redacted root without a message storm, and use the same underlying action model that 0.6.0b2 Widget will consume.
