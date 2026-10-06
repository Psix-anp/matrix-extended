# Matrix Native Widget Design for 0.6.0b2

## Status

Design approved in chat on 2026-09-28. This written specification is the review artifact before implementation planning begins.

## Goal

Add a graphical Matrix Widget control surface to Matrix Extended without giving the Widget a Home Assistant access token, without exposing arbitrary Home Assistant services to Matrix, and without replacing the reaction-based Native Matrix Control introduced in `0.6.0b1`.

The Widget reuses the existing account allowlists, panel definitions, runtime generation, confirmation model, and Safe Action execution boundary. It is an additional adapter over the same control plane, not a second authorization/execution system.

## Scope

`0.6.0b2` includes:

- one Widget surface linked to an existing Matrix Extended control panel;
- Matrix Widget API communication;
- Matrix to-device signalling for Widget state/actions;
- no Home Assistant token in the Widget;
- account room/user allowlist enforcement and panel-level user restrictions;
- panel generation validation and request de-duplication;
- explicit bounded entity controls;
- existing configured panel actions exposed as Widget buttons;
- the existing dangerous-action confirmation model;
- live state refresh from actual Home Assistant state;
- reconnect/reload behavior without stale action replay;
- a versioned static Widget bundle with self-hosting support;
- Russian and English UI;
- browser E2E against the real HA + Synapse + Element stack;
- startup hardening for missing/unavailable E2EE runtime dependencies;
- updated stable compatibility pins when implementation begins.

Not in `0.6.0b2`:

- arbitrary Lovelace dashboards;
- arbitrary HA service/target/data supplied by Matrix;
- arbitrary Jinja/YAML supplied by the Widget;
- camera/video streaming or Media Browser;
- history graphs or drag-and-drop dashboard editing;
- automatic Matrix room/Space creation;
- cross-signing/sliding-sync work;
- mandatory use of experimental sticky/state Widget APIs.

## Architectural Decision: To-Device Transport

Use Matrix **to-device events** for Widget signalling.

The Widget runs inside a compatible Matrix client and requests narrowly scoped Widget API capabilities for one Matrix Extended custom to-device event type. The Matrix client performs the authenticated Matrix operation.

This deliberately avoids custom room timeline traffic. Widget protocol messages should not create visible timeline noise and should not require the integration account to have room-state power merely to exchange live control data.

The existing reaction panel stays independent and usable as fallback.

### Exact integration device targeting

Widget -> Matrix Extended traffic MUST target the exact Matrix Extended device ID, not `*`.

The generated Widget configuration contains these non-secret identifiers:

- Matrix Extended Matrix user ID;
- Matrix Extended Matrix device ID;
- panel ID;
- room ID via Matrix Widget URL templating/configuration.

This prevents a second active device logged into the same Matrix bot account from receiving and potentially executing the same control request.

Matrix Extended -> authorized user state/result traffic may target device `*`: duplicate delivery to a user's other Matrix devices is harmless because only an active matching Widget consumes the custom event.

## Widget API Compatibility Boundary

Widgets are not yet a final Matrix-spec feature. Widget support is therefore capability-gated, not required for the integration itself.

The frontend requests only:

- `org.matrix.msc3819.send.to_device:io.psix.matrix_extended.widget.v1`;
- `org.matrix.msc3819.receive.to_device:io.psix.matrix_extended.widget.v1`.

If the current client refuses or lacks the required capability, the Widget displays an unsupported-client state and directs the user to the reaction-panel fallback.

Experimental sticky/state Widget capabilities are not a hard dependency for b2.

## Protocol

Custom Matrix to-device event type:

```text
io.psix.matrix_extended.widget.v1
```

Common fields:

```json
{
  "schema": 1,
  "op": "subscribe",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "request_id": "optional-uuid"
}
```

`generation` is deliberately absent from the initial `subscribe`: a newly opened Widget does not know the current generation until Matrix Extended returns its first state snapshot.

Allowed operations:

- `subscribe` - request current state/live updates;
- `heartbeat` - refresh subscription TTL;
- `state` - full bounded current state snapshot;
- `action` - request one bounded entity control or existing configured panel action;
- `confirm` - confirm/cancel one pending confirmation;
- `result` - bounded action result;
- `error` - bounded/redacted protocol or authorization error.

Unknown schema versions or operations are rejected fail-closed.

No request may carry an arbitrary `domain.service`, arbitrary HA target, Jinja expression, or unrestricted service-data mapping for execution.

## Subscription Model

Widget state delivery is opt-in and ephemeral.

On load, Widget sends `subscribe` to the exact Matrix Extended device. Matrix Extended authenticates the Matrix sender and validates the requested room/panel before creating an in-memory subscription.

Subscription key:

```text
(panel_id, matrix_user_id)
```

Rules:

- not persisted across HA restart/reload;
- immediate full snapshot after successful subscribe;
- heartbeat refreshes TTL;
- expired subscriptions are discarded;
- only authorized subscribed users receive state;
- state/result/error responses target the subscribed Matrix user with device `*`;
- other devices ignore the custom event unless they host a matching Widget.

Initial timing target:

- heartbeat: 30 s;
- TTL: 90 s.

Exact timing may be tuned by tests without changing protocol semantics.

## State Snapshot

Home Assistant is always the source of truth.

Send a complete bounded snapshot, not incremental patches. Panels are intentionally small; full snapshots make reconnect and missed-message recovery deterministic.

Example:

```json
{
  "schema": 1,
  "op": "state",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "generation": 7,
  "revision": 42,
  "title": "Гостиная",
  "entities": [
    {
      "entity_id": "light.living_room",
      "label": "Свет",
      "domain": "light",
      "state": "on",
      "available": true,
      "attributes": {"brightness_pct": 65},
      "controls": ["toggle", "brightness"]
    }
  ],
  "actions": [
    {
      "id": "movie_scene",
      "label": "Кино",
      "confirmation_required": false
    }
  ]
}
```

This is a presentation/control contract, not a raw HA state dump. Only attributes required by supported adapters are emitted. Secrets and unrelated attributes are omitted.

The Widget renders controls from the server-provided `controls` list; it must not infer permission merely from the entity domain.

## Entity Control Policy

Displaying an entity does not automatically make it controllable.

Per-entity Widget controls are explicitly enabled in panel configuration. The GUI offers domain-appropriate choices.

Initial adapters:

### light

- `toggle`;
- `brightness` when supported.

Brightness accepts integer percent `0..100` and is converted locally to a fixed-entity HA service call.

### switch

- `toggle`.

### cover

- `open`;
- `close`;
- `stop`;
- `position` when supported (`0..100`).

All cover controls are opt-in because a cover can be curtains, a gate, or a garage door. Confirmation can be enabled per control.

### climate

- target temperature;
- supported HVAC mode selection.

Temperature is validated against current HA min/max/step capability.

### sensor / binary_sensor

Read-only.

### media_player

Where HA reports support:

- play/pause;
- previous/next;
- mute;
- bounded volume.

### high-risk domains

`lock` and `alarm_control_panel` are not generic auto-controls in the first MVP. Use existing explicitly configured `PanelAction` definitions with confirmation until dedicated adapters are designed and tested.

## Existing Panel Actions

Existing `PanelAction` definitions remain authoritative and can be rendered as Widget buttons.

Widget request contains only the stable action ID and protocol context:

```json
{
  "schema": 1,
  "op": "action",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "generation": 7,
  "request_id": "uuid",
  "kind": "panel_action",
  "action_id": "movie_scene"
}
```

The backend resolves the action against current local configuration. Service/target/data never come from the Widget.

## Parameterized Entity Controls

Sliders/selectors use bounded server-defined intents, not arbitrary service-data overrides.

Example:

```json
{
  "schema": 1,
  "op": "action",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "generation": 7,
  "request_id": "uuid",
  "kind": "entity_control",
  "entity_id": "light.living_room",
  "control": "brightness",
  "value": 65
}
```

Before execution, backend verifies:

1. panel is enabled/current;
2. sender passes account allowlist;
3. room passes account allowlist;
4. panel is configured for that room;
5. sender passes panel-level restriction;
6. generation matches current runtime generation;
7. entity is configured on the panel;
8. requested control is explicitly enabled;
9. domain matches the control adapter;
10. value passes adapter schema/range/current HA capability;
11. any required confirmation is satisfied.

Only then is a local HA service call constructed.

## Confirmation Flow

The existing confirmation model remains canonical, but its storage becomes transport-neutral.

For a Widget action requiring confirmation:

1. Widget sends action request;
2. backend creates a pending confirmation bound to sender, panel/action-or-control identity, generation, and request ID;
3. backend returns `confirmation_required` plus a short-lived opaque `confirmation_id`;
4. Widget renders Confirm / Cancel with the existing 30-second timeout;
5. Widget sends `confirm` referencing that ID;
6. backend revalidates same sender and active generation before execution.

`confirmation_id` is single-use and in-memory only. HA restart/reload invalidates it.

Reaction-panel confirmations continue to use the existing Matrix reply/reaction flow. Both paths share the same safety invariants, not necessarily the same presentation token.

## Result Handling

Each Widget action has a Widget-generated `request_id`.

High-level result statuses:

- `accepted`;
- `confirmation_required`;
- `cancelled`;
- `rejected`;
- `failed`.

A successful service call is not proof of final device state. UI state changes only from subsequent actual HA state snapshots.

Errors sent to Widget are bounded/redacted. Never send tokens, stored service data, raw exception dumps, or provider secrets.

## Security and Replay Rules

All Widget payload fields are untrusted input.

Backend revalidates sender, room, panel, generation, entity/control/action and value against current local state.

Additional replay protections:

- stale generation rejected;
- request IDs de-duplicated in a bounded in-memory window per sender/panel;
- confirmations single-use and expiring;
- state revision is ordering metadata only, never authorization;
- Widget requests target the exact configured Matrix Extended device ID;
- control requests are never placed in the persistent outbound notification queue.

To-device transport is signalling, not the authorization boundary.

## needs_repair Behavior

If the underlying Native Control panel runtime is `needs_repair`, Widget remains diagnostic/read-only for that panel and rejects control actions until the user performs the existing explicit Repair flow.

Repair advances panel generation. Any Widget action carrying the previous generation is rejected.

This keeps one lifecycle and prevents Widget control from silently bypassing a broken/replaced reaction-panel root.

## Widget Frontend

Use a small TypeScript frontend without a heavyweight UI framework for the MVP.

Suggested layout:

```text
widget/
  package.json
  tsconfig.json
  src/
    index.ts
    matrix.ts
    protocol.ts
    model.ts
    controls/
    i18n/
    styles.css
  tests/
  dist/
```

Frontend responsibilities:

- instantiate `matrix-widget-api`;
- request only required to-device capabilities;
- read room/user/widget context from Widget URL templating/config;
- read Matrix Extended user/device ID from non-secret generated Widget config;
- subscribe on startup and heartbeat while active;
- render full snapshots;
- correlate results by request ID;
- render only server-advertised controls;
- show confirmation, capability, authorization and offline states;
- never store HA credentials.

UI target: compact, touch-friendly, keyboard accessible, dark/light adaptive, usable in Element desktop/mobile Widget surfaces.

## Distribution and Hosting

Release pipeline builds a versioned static bundle:

```text
matrix_extended-widget-v0.6.0b2.zip
```

The Widget base URL is configurable so the same bundle can be self-hosted.

An official hosted deployment may be provided, but protocol correctness must not depend on a mutable `latest` URL. Versioned Widget assets should remain compatible with protocol schema 1.

No HA or Matrix access token is embedded in Widget URL/configuration.

## Home Assistant Configuration UX

Under Native Matrix Control, add Widget configuration for a panel:

- enabled/disabled;
- Widget base URL;
- enabled controls per entity;
- confirmation requirements where applicable;
- generated Widget URL/config;
- Matrix Extended user ID and current device ID embedded as non-secret routing metadata;
- compatibility/diagnostic status.

Automatic insertion of a Widget into a room is optional for b2 and only allowed when the integration account already has the required room-state power. Failure must not affect the reaction panel.

If cross-client auto-install semantics are unreliable, b2 ships a generated URL/config and a documented manual add step rather than changing power levels or inventing client-specific unsafe behavior.

## Backend Components

Existing `ControlPanelManager`, `ControlPanelRuntimeStore`, `PendingConfirmationRegistry`, panel definitions, and `SafeActionExecutor` stay authoritative.

New responsibilities:

```text
widget_protocol.py
  schema validation and bounded parsing/dumping

widget_sessions.py
  subscriber TTL, request dedupe, revisions

widget_controls.py
  domain adapters, snapshot projection, bounded control validation

widget_transport.py
  Matrix custom to-device send/receive only

widget/
  TypeScript frontend
```

Widget code should reuse ControlPanelManager authorization/state/execution hooks rather than duplicate root lifecycle logic.

## Matrix Client Changes

Add bounded wrapper capabilities for:

- custom to-device callback registration;
- sending a custom to-device event to a specific user/device set;
- exact-device Widget -> integration routing;
- user `*` delivery for state/results;
- preserving existing E2EE/key housekeeping.

Before choosing encrypted vs plaintext custom to-device payloads, run an explicit interoperability probe with matrix-nio 0.26.0 and the pinned Element version.

If encrypted custom to-device events work reliably end-to-end, use them. If not, plaintext to-device may be used only because protocol payloads contain no access tokens or arbitrary service payloads and authorization is still sender/room/panel based. The release notes must state the tested transport behavior.

## E2EE Runtime Preflight Hardening

Before constructing an E2EE-enabled `AsyncClientConfig`, detect whether the E2EE runtime is actually usable.

Requirements:

- do not leave a raw matrix-nio `ImportWarning` as the only explanation;
- log a direct dependency/runtime message;
- fail closed when E2EE is required;
- expose a HA repair/config-entry diagnostic path where feasible;
- regression-test `nio.crypto.ENCRYPTION_ENABLED == False`;
- keep `matrix-nio[e2e]` / `vodozemac` explicit in manifest requirements.

## State Update and Outage Flow

```text
HA state change
  -> existing panel debounce/state path
  -> reaction panel update as today
  -> bounded Widget snapshot projection
  -> snapshot hash compare
  -> latest full snapshot to active subscribers
```

Do not send a state message when projected state did not change.

During Matrix outage, do not queue every Widget snapshot. Keep current HA state; after reconnect the next subscribe/heartbeat/refresh gets one current snapshot.

Widget control actions are never persisted for later execution. If they cannot be processed live, they fail visibly.

## Restart and Recovery

On HA restart/reload:

- panel config/runtime generation restore as b1;
- pending confirmations drop;
- Widget subscriptions drop;
- request dedupe cache drops;
- existing reaction-panel root remains stable;
- no Widget action replays;
- open Widget re-subscribes and receives fresh state.

## Diagnostics

Extend disabled-by-default control-panel diagnostics with bounded Widget fields:

- enabled;
- protocol schema;
- active subscriber count;
- last subscribe/state-send timestamps;
- last bounded transport error;
- last action kind/status;
- capability/compatibility state where observable.

Never expose tokens, raw service data, confirmation secrets, or raw sensitive payloads.

## Compatibility and CI

When implementation starts, update real-stack pins to the then-current stable:

- Home Assistant 2026.9.x;
- Synapse stable;
- Element Web stable.

Keep the b1 stack as a regression reference where practical. An optional non-blocking lane may track the next upstream RC, but upstream pre-releases are not publication gates.

## Test Strategy

### Backend tests

- protocol schema/rejection;
- exact integration device routing;
- account and panel authorization;
- generation checks;
- request dedupe;
- subscribe/heartbeat/expiry;
- bounded state projection;
- secret/attribute filtering;
- each entity adapter and range validation;
- existing PanelAction resolution;
- confirmation create/confirm/cancel/expiry;
- needs_repair read-only behavior;
- state no-op suppression;
- restart semantics;
- E2EE preflight failure.

### Frontend tests

- capability grant/denial;
- subscribe/heartbeat;
- snapshot rendering;
- read-only/unsupported rendering;
- buttons/sliders/selectors;
- result correlation;
- confirmation UI;
- stale-generation refresh;
- offline/unsupported-client states;
- Russian/English strings.

### Real-stack browser E2E publication gate

1. install exact build artifact;
2. connect Matrix Extended with E2EE healthy;
3. use Native Control panel;
4. load Widget in Element iframe;
5. grant required capabilities;
6. subscribe and receive current HA state;
7. HA state change refreshes Widget;
8. Widget toggles light and actual HA state changes;
9. one bounded numeric control works;
10. one existing panel action works;
11. confirmation-required action works and cannot be bypassed;
12. unauthorized sender rejected;
13. wrong room/panel rejected;
14. stale generation rejected;
15. `needs_repair` is read-only until Repair;
16. HA restart -> re-subscribe/current state, no replay;
17. Synapse outage/recovery -> no stale action replay;
18. reaction fallback still works;
19. Widget protocol creates no visible room timeline spam;
20. no background-task leaks;
21. package integrity, HACS and Hassfest pass.

## Release Packaging

`0.6.0b2` is a Pre-release.

Artifacts:

- HA install ZIP + SHA256;
- versioned Widget bundle ZIP + SHA256 when cleanly supported by release tooling.

Release notes must state:

- Widget is beta;
- tested Matrix clients;
- custom to-device encryption behavior;
- manual/automatic installation limitations;
- reaction panel remains supported;
- Widget receives no HA access token.

## Acceptance Criteria

Publish only when:

- all b1 reaction-panel behavior stays green;
- initial domains display live state;
- explicitly enabled bounded controls execute;
- configured panel actions execute;
- dangerous actions cannot bypass confirmation;
- arbitrary Matrix payloads cannot select arbitrary HA service/target/data;
- duplicate/stale/replay tests pass;
- exact-device integration routing is verified;
- outage/restart proves no delayed control execution;
- Widget receives no HA token;
- room timeline remains clean;
- E2EE preflight gives a clear dependency/runtime failure;
- real-stack browser E2E passes;
- HACS/Hassfest pass;
- install and Widget artifacts are verified.

## Deferred After 0.6.0b2

Candidate b3/later work:

- richer media metadata/artwork;
- dedicated lock/alarm adapters;
- camera snapshot tiles;
- multiple pages/sections;
- configurable layouts/history graphs;
- room/Space provisioning;
- broader auto-install support;
- optional sticky-event optimization when mature;
- broader Matrix client compatibility beyond the tested Element path.
