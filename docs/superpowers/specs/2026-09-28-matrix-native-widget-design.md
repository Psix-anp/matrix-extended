# Matrix Native Widget Design for 0.6.0b2

## Status

Design approved in chat on 2026-09-28. This written specification is the review artifact before implementation planning begins.

## Goal

Add a graphical Matrix Widget control surface to Matrix Extended without giving the Widget a Home Assistant access token, without exposing arbitrary Home Assistant services to Matrix, and without replacing the reaction-based Native Matrix Control introduced in `0.6.0b1`.

The Widget must reuse the same account allowlists, panel definitions, runtime generation model, confirmation model, and Safe Action execution boundary that already protect Native Matrix Control.

The Widget is an additional input/output adapter over the existing control plane, not a second control system.

## Product Outcome

A configured Matrix room can show a graphical Home Assistant panel inside a compatible Matrix client. The first beta supports useful controls for common entity domains while keeping Home Assistant as the source of truth.

The user can continue using the existing pinned reaction panel if the Matrix client does not support Widgets, if the Widget is unavailable, or if the user simply prefers the fallback.

## Scope

`0.6.0b2` includes:

- one Widget surface linked to an existing Matrix Extended control panel;
- no direct Home Assistant API token in the Widget;
- Matrix Widget API based communication;
- Matrix to-device signalling between the Widget user's Matrix client and the Matrix Extended account;
- account room/user allowlist enforcement;
- panel-level user restrictions;
- panel generation validation;
- explicit low-risk entity controls;
- existing predefined panel actions exposed as Widget buttons;
- confirmation for actions that already require confirmation;
- live state refresh from actual Home Assistant state;
- reconnect/reload behavior without replaying stale control operations;
- a versioned static Widget bundle and self-hosting support;
- English and Russian UI strings;
- diagnostics and real-stack browser E2E coverage;
- clearer E2EE runtime/preflight failure reporting when `vodozemac` is unavailable;
- updated real-stack compatibility pins for the current stable Home Assistant, Synapse, and Element versions selected when implementation starts.

`0.6.0b2` does not include:

- arbitrary Lovelace dashboards;
- arbitrary Home Assistant service calls supplied by the Widget;
- arbitrary Jinja/YAML supplied by the Widget;
- camera or video streaming;
- Media Browser;
- history graphs;
- drag-and-drop dashboard editing;
- automatic Space creation;
- automatic Matrix room creation;
- cross-signing work;
- sliding-sync work;
- a requirement that the Widget replace the existing reaction panel;
- experimental Matrix Widget features as a hard dependency when stable-compatible behaviour is available.

## Architectural Decision

Use Matrix **to-device signalling** as the Widget transport.

The Widget runs inside a Matrix client and requests narrowly-scoped Widget API capabilities to send and receive one Matrix Extended custom to-device event type. The Matrix client performs the actual authenticated Matrix send/receive operation.

The Widget never receives a Home Assistant long-lived access token and never calls Home Assistant service APIs directly.

The transport is intentionally not a custom room timeline event. This avoids timeline pollution, does not require custom state-event power levels, and matches the Matrix specification's intended use of send-to-device events for signalling data that should not persist in the room DAG.

The existing reaction panel remains available and independent. A failure of the Widget transport must not break reaction control.

## Widget API Compatibility Boundary

Widgets are still outside the final Matrix specification. Matrix Extended therefore treats Widget support as a client capability, not as a requirement for the integration.

The frontend uses `matrix-widget-api` and requests only the capabilities required for the Matrix Extended custom to-device event type:

- send to-device for the Matrix Extended Widget protocol event;
- receive to-device for the Matrix Extended Widget protocol event.

The implementation must verify the capability grant at runtime. If the current Matrix client refuses or lacks those capabilities, the Widget shows a clear unsupported-client state and points the user back to the reaction panel.

Experimental sticky/state Widget APIs may be investigated for later optimization, but `0.6.0b2` must not require them.

## Protocol Event

Use one namespaced to-device event type for protocol version 1:

```text
io.psix.matrix_extended.widget.v1
```

The direction and `op` field determine the message purpose.

Common envelope:

```json
{
  "schema": 1,
  "op": "subscribe",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "generation": 7,
  "request_id": "optional-uuid"
}
```

Allowed operations:

- `subscribe` — Widget asks for the current panel snapshot and live refreshes;
- `heartbeat` — refreshes the ephemeral subscription TTL;
- `state` — Matrix Extended sends a complete current state snapshot;
- `action` — Widget requests one bounded control intent or existing configured panel action;
- `result` — Matrix Extended returns a bounded result for a request;
- `error` — Matrix Extended returns a bounded/redacted protocol or authorization error.

No protocol message may carry an arbitrary Home Assistant `domain.service`, target object, Jinja expression, or unrestricted service data object for execution.

Unknown schema versions or operations are rejected fail-closed.

## Subscription Model

Widget state delivery is opt-in and ephemeral.

When a Widget opens it sends `subscribe` with its room and panel identifiers. Matrix Extended validates the Matrix sender and the requested panel before creating an in-memory subscription.

Subscription key:

```text
(panel_id, matrix_user_id)
```

Properties:

- subscriptions are not persisted across Home Assistant restart;
- a successful subscribe immediately returns a full state snapshot;
- the Widget sends a heartbeat periodically;
- a subscription expires after a bounded TTL when heartbeats stop;
- Matrix Extended sends state only to currently subscribed authorized users;
- delivery targets `*` for the subscribed Matrix user so the active Matrix client device receives the update without needing a separate device-registration protocol;
- other devices for the same Matrix user may receive the unknown custom to-device event and are expected to ignore it unless they host an active matching Widget.

Recommended initial timing:

- heartbeat every 30 seconds;
- subscription TTL 90 seconds.

The exact constants may be tuned by tests without changing the protocol contract.

## State Snapshot

Home Assistant remains the source of truth.

Matrix Extended sends a complete bounded snapshot rather than incremental patches. Panels are intentionally small, and complete snapshots make reconnect and missed-message recovery deterministic.

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
      "attributes": {
        "brightness_pct": 65
      },
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

The snapshot is a presentation/control contract, not a raw Home Assistant state dump.

Only attributes required by the supported adapter are included. Secrets and unrelated entity attributes are omitted.

Each snapshot contains:

- panel ID;
- room ID;
- active panel generation;
- monotonically increasing in-process revision;
- localized/selected labels;
- bounded per-domain state;
- the list of controls the server currently permits;
- existing configured panel actions suitable for Widget buttons.

The Widget never assumes an operation is permitted solely from the entity domain. It renders controls from the server-provided `controls` list.

## Entity Control Policy

Displaying an entity does not automatically grant every possible control for that domain.

Per-entity Widget controls are explicitly enabled in panel configuration. The GUI should offer domain-appropriate choices and store only the selected control capabilities.

Initial adapters:

### `light`

Supported controls:

- `toggle`;
- `brightness` when supported by the entity.

`brightness` accepts an integer percentage `0..100`. Matrix Extended converts it locally to the Home Assistant service payload for the fixed configured entity.

### `switch`

Supported controls:

- `toggle`.

### `cover`

Supported controls:

- `open`;
- `close`;
- `stop`;
- `position` when supported.

`position` accepts integer `0..100`.

Cover controls are opt-in because a cover may represent curtains, a gate, or a garage door. Configuration can require confirmation for selected controls.

### `climate`

Supported controls:

- target temperature;
- supported HVAC mode selection where safe and available.

Temperature values are validated against the entity's current Home Assistant min/max/step capabilities before execution.

### `sensor`

Read-only.

### `binary_sensor`

Read-only.

### `media_player`

Supported controls where the entity reports support:

- play/pause;
- previous/next;
- mute;
- volume.

Volume is a normalized bounded value and is converted locally to the Home Assistant service format.

### Deferred/high-risk domains

`lock` and `alarm_control_panel` are not exposed as generic automatic controls in the first Widget MVP. They may be represented through existing configured panel actions with `confirmation_required: true` until a dedicated high-risk adapter is designed and tested.

## Existing Panel Actions

Existing `PanelAction` definitions remain valid.

The Widget may render each configured action as a button. When pressed it sends only the stable action ID plus protocol context.

Example:

```json
{
  "schema": 1,
  "op": "action",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "generation": 7,
  "request_id": "d8d43d7e-...",
  "kind": "panel_action",
  "action_id": "movie_scene"
}
```

Matrix Extended resolves `movie_scene` against the current local panel definition. The Widget does not provide the service, target, or stored action data.

## Parameterized Control Intents

Interactive sliders and selectors require bounded parameters. They are not implemented as arbitrary service-data overrides.

Example brightness request:

```json
{
  "schema": 1,
  "op": "action",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "generation": 7,
  "request_id": "5a7f...",
  "kind": "entity_control",
  "entity_id": "light.living_room",
  "control": "brightness",
  "value": 65
}
```

The backend must verify all of the following:

1. the panel is current and enabled;
2. the sender is authorized for the account;
3. the room is authorized for the account;
4. the panel belongs to that room;
5. the sender passes panel-level restrictions;
6. the generation matches the active runtime generation;
7. the entity is explicitly configured on the panel;
8. the requested control is explicitly enabled for that entity;
9. the entity's domain matches the adapter;
10. the value matches the adapter schema/range/capability;
11. any configured confirmation requirement is satisfied.

Only then does the backend construct the Home Assistant service call locally.

## Confirmation Flow

The existing Native Matrix Control confirmation model remains the canonical dangerous-action model.

For an action/control requiring confirmation:

1. Widget sends the initial action request;
2. backend creates a pending confirmation bound to sender, panel ID, action/control identity, generation, and request ID;
3. Widget receives a result indicating `confirmation_required`;
4. Widget renders explicit Confirm / Cancel controls with the existing 30-second timeout;
5. Widget sends a bounded confirm/cancel operation referencing the pending confirmation identifier;
6. backend verifies the same Matrix sender and active generation before execution.

A Home Assistant restart/reload invalidates pending confirmations.

The existing reaction-based `✅` / `❌` flow remains valid for reaction-panel actions. Widget confirmation does not weaken or bypass it.

## Result Handling

Every Widget action contains a `request_id` generated by the Widget.

Backend returns a bounded result:

```json
{
  "schema": 1,
  "op": "result",
  "room_id": "!room:example.org",
  "panel_id": "living",
  "generation": 7,
  "request_id": "5a7f...",
  "status": "accepted"
}
```

Possible high-level statuses include:

- `accepted`;
- `confirmation_required`;
- `cancelled`;
- `rejected`;
- `failed`.

Successful service execution is not treated as proof that the physical entity reached the requested final state. The Widget reflects actual Home Assistant state from the next `state` snapshot.

Errors are bounded and sanitized. Tokens, stored service data, raw exception dumps, and sensitive provider responses must not be sent to the Widget.

## Security Model

Authorization remains fail-closed.

A Widget action is accepted only if the authenticated Matrix sender is allowed at the account level and, when configured, at the panel level.

`room_id` in the to-device payload is untrusted input. The backend verifies it against the configured panel and account room allowlist.

`panel_id`, `entity_id`, `control`, `action_id`, `generation`, and all values are untrusted input and are revalidated against current local configuration/runtime state.

The protocol never trusts Widget-rendered state as authoritative.

Replay resistance:

- stale panel generations are rejected;
- request IDs are bounded-deduplicated for a short in-memory window per sender/panel;
- confirmation identifiers are single-use;
- pending confirmations expire;
- state revisions are presentation ordering only and never authorization tokens.

To-device delivery is signalling transport, not the authorization boundary.

## Widget Frontend

Use a small TypeScript frontend without a heavyweight UI framework for the MVP.

Repository layout:

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

The frontend should:

- instantiate `matrix-widget-api`;
- request only the required to-device capabilities;
- derive room/user/widget context from Matrix Widget URL templating and configured widget data;
- subscribe on startup;
- refresh the subscription with heartbeat;
- render complete snapshots;
- correlate action results with request IDs;
- disable or hide controls not present in the server snapshot;
- show connection/capability/authorization errors clearly;
- never store Home Assistant credentials;
- contain no provider-specific Home Assistant secrets.

The initial visual style is compact, touch-friendly, keyboard accessible, dark/light adaptive, and suitable for Element desktop/mobile Widget surfaces.

## Widget Distribution and Hosting

The release pipeline builds a versioned static Widget bundle.

Required release artifact:

```text
matrix_extended-widget-v0.6.0b2.zip
```

The Widget URL is configurable in Matrix Extended so users can self-host the exact same static bundle.

The project may publish an official versioned static deployment, but protocol correctness must not depend on a mutable `latest` URL. A room/panel should be able to point at a versioned Widget bundle compatible with the backend protocol schema.

The Widget URL contains no Home Assistant token or Matrix access token.

Room/user/widget identifiers should use Matrix Widget URL-template substitution where supported. Sensitive data must not be placed in query parameters or fragments.

## Widget Installation UX

The Home Assistant Options Flow gains a Widget subsection under Native Matrix Control.

At minimum it provides:

- Widget enabled/disabled for a panel;
- Widget base URL;
- enabled per-entity Widget controls;
- confirmation policy for controls that require it;
- generated Matrix Widget URL/configuration data;
- current Widget protocol compatibility/diagnostic status.

Automatic insertion of the Widget into the Matrix room is optional for `0.6.0b2` and must only be attempted when the Matrix account has the required room-state power. Failure to auto-install must not break the panel.

If reliable cross-client Widget state-event installation semantics are not available, `0.6.0b2` may ship with a generated configuration/URL and a documented manual add step rather than modifying room power levels or inventing unsafe behaviour.

## Backend Components

The existing `ControlPanelManager`, `ControlPanelRuntimeStore`, `PendingConfirmationRegistry`, panel definitions, and `SafeActionExecutor` remain authoritative.

New responsibilities should be isolated approximately as:

```text
widget_protocol.py
  schema validation
  bounded message parsing/dumping

widget_sessions.py
  subscriber TTLs
  request dedupe
  state revision tracking

widget_controls.py
  domain adapters
  supported state projection
  bounded control validation
  local HA service-call construction

widget_transport.py
  Matrix to-device send/receive adapter
  no authorization policy of its own

widget/
  static TypeScript frontend
```

`ControlPanelManager` should expose/reuse current panel state and authorization/execution hooks rather than duplicate root-message lifecycle logic in the Widget code.

## Matrix Client Changes

The Matrix client wrapper needs bounded helpers for custom to-device traffic and callbacks.

Required capabilities:

- register a to-device callback for the Matrix Extended Widget protocol event;
- send a custom to-device event to a user, targeting `*` devices;
- preserve existing matrix-nio E2EE/key-maintenance behaviour;
- keep Widget signalling independent of room-event outbox semantics.

The implementation must test how matrix-nio 0.26.0 exposes custom encrypted and unencrypted to-device events before deciding whether protocol messages are sent with to-device encryption enabled in the first beta.

If encrypted custom to-device interoperability is reliable in the tested Element + matrix-nio stack, use it. If not, the protocol may use plaintext to-device transport only after confirming that no secrets/service payloads are present and all authorization remains sender/room/panel based. This choice must be documented explicitly in the release notes.

## E2EE Runtime Preflight Hardening

`0.6.0b2` also hardens the integration startup path based on the observed `0.5.8` field failure where matrix-nio raised a raw `ImportWarning` because its E2EE runtime dependency was not visible at import time.

Before constructing an E2EE-enabled `AsyncClientConfig`, Matrix Extended must detect and report whether the E2EE runtime is actually usable.

Requirements:

- no raw `ImportWarning` traceback as the only user-facing explanation;
- log a direct message naming the missing/unavailable E2EE runtime dependency;
- fail closed when E2EE is required;
- expose a Home Assistant repair/config-entry diagnostic path where feasible;
- add a regression test that simulates `nio.crypto.ENCRYPTION_ENABLED == False`;
- keep the manifest requirement for `matrix-nio[e2e]` / `vodozemac` explicit.

This is diagnostics/hardening, not a relaxation of E2EE policy.

## State Update Flow

Widget state follows the existing event-driven Home Assistant model.

```text
HA state change
  -> existing panel debounce/dirty path
  -> render/update reaction panel as today
  -> project bounded Widget snapshot
  -> compare Widget snapshot hash/revision
  -> send latest complete snapshot to active subscribers only
```

The backend should not emit a Widget state message when the projected snapshot is unchanged.

During Synapse/Matrix outage, stale Widget snapshots are not queued individually. The backend retains current Home Assistant state. After reconnection, the next subscribe/heartbeat/current-state refresh sends one current complete snapshot.

Widget actions are not stored in the persistent outbound notification outbox. A control request must either be processed in the live session or fail visibly; it must never execute minutes later merely because Matrix connectivity returned.

## Restart and Recovery

On Home Assistant restart/reload:

- panel configuration and runtime generation restore as in `0.6.0b1`;
- pending confirmations are dropped;
- Widget subscriptions are dropped;
- request dedupe cache is dropped;
- the existing Matrix control root remains stable;
- no Widget action is replayed;
- an open Widget re-subscribes and receives a fresh complete snapshot.

If the panel root is `needs_repair`, the Widget may still show diagnostic state but must not bypass the explicit Repair lifecycle for the reaction panel root.

A repaired panel advances generation. Old Widget actions carrying the previous generation are rejected.

## Diagnostics

Extend the disabled-by-default control-panel diagnostic data with bounded Widget information:

- Widget enabled;
- protocol schema version;
- active subscriber count;
- last subscribe timestamp;
- last state-send timestamp;
- last bounded Widget transport error;
- last action status/action kind without service payload;
- capability/compatibility state where observable.

Do not expose:

- Matrix access tokens;
- HA tokens;
- raw service data;
- confirmation secrets/identifiers beyond what is safe for diagnostics;
- raw to-device contents containing user-provided values beyond bounded non-sensitive summaries.

## Compatibility and CI

At implementation start, update the real-stack test pins to the then-current stable versions of:

- Home Assistant 2026.9.x;
- Synapse stable;
- Element Web stable.

Keep the previous `0.6.0b1` tested stack available as a regression reference where practical.

An optional non-blocking compatibility lane may track the next Synapse/Element release candidate, but pre-release upstream software must not become a publication gate for Matrix Extended stable/beta releases.

## Test Strategy

### Python unit/contract tests

Cover:

- protocol schema parsing and rejection;
- sender/room/panel authorization;
- panel-level restrictions;
- generation checks;
- request dedupe;
- subscription TTL and heartbeat;
- snapshot projection and secret/attribute filtering;
- each entity-domain adapter;
- parameter range validation;
- unsupported control rejection;
- existing PanelAction resolution;
- confirmation creation/confirm/cancel/expiry;
- state hash/no-op suppression;
- restart semantics;
- E2EE runtime preflight failure.

### Widget frontend tests

Cover:

- capability request/grant/denial;
- subscribe/heartbeat lifecycle;
- full snapshot rendering;
- unsupported/read-only entity rendering;
- button actions;
- sliders/selectors with debouncing where appropriate;
- pending result UI;
- confirmation UI;
- stale generation refresh;
- offline/unsupported-client messages;
- Russian/English strings.

### Real-stack E2E

The publication gate must exercise a real Home Assistant + Synapse + Element Web stack and an actual Widget iframe.

Required scenarios:

1. install exact build artifact;
2. connect Matrix Extended with E2EE runtime healthy;
3. create/use a Native Control panel;
4. load the Widget in Element;
5. grant required Widget capabilities;
6. subscribe and receive current HA state;
7. change HA state and observe Widget refresh;
8. toggle a light from Widget and observe actual HA state then Widget refresh;
9. exercise one bounded numeric control, such as brightness;
10. execute one existing configured panel action;
11. exercise a confirmation-required action;
12. reject unauthorized sender;
13. reject unauthorized room/panel combination;
14. reject stale generation;
15. restart Home Assistant and verify re-subscribe/current state;
16. stop/restart Synapse and verify no stale action replay;
17. verify reaction-panel control still works;
18. verify Widget protocol traffic does not create user-visible room timeline spam;
19. verify no background task leaks;
20. verify package integrity, HACS validation, and Hassfest.

## Release Packaging

`0.6.0b2` remains a GitHub Pre-release.

Release artifacts include at least:

- Home Assistant install ZIP;
- install ZIP SHA256;
- versioned Widget static bundle ZIP;
- Widget bundle SHA256 when release tooling supports it cleanly.

Release notes must state:

- Widget support is beta;
- tested Matrix clients;
- whether to-device payload transport is encrypted in the tested implementation;
- manual/automatic Widget installation limitations;
- reaction panel remains supported fallback;
- no Home Assistant token is given to the Widget.

## Acceptance Criteria

`0.6.0b2` is publishable only when all of the following are true:

- existing `0.6.0b1` reaction-panel behaviour remains green;
- Widget can display live state for the initial domain set;
- Widget can execute explicitly enabled bounded controls;
- Widget can execute existing predefined panel actions;
- dangerous actions cannot bypass confirmation;
- arbitrary Matrix payloads cannot select arbitrary HA services/targets/data;
- stale generation/replayed request tests pass;
- restart/outage tests prove no delayed action execution;
- Widget receives no HA access token;
- timeline-spam E2E check passes;
- E2EE runtime preflight produces a clear failure instead of the raw dependency `ImportWarning` path;
- real-stack browser E2E passes on the pinned current-stable test matrix;
- HACS and Hassfest pass;
- release install ZIP and Widget bundle are verified before publication.

## Deferred Work After 0.6.0b2

Candidate work for `0.6.0b3` or later:

- richer `media_player` metadata and artwork;
- dedicated `lock` adapter;
- dedicated `alarm_control_panel` adapter;
- camera snapshot tiles;
- multiple Widget pages/sections;
- configurable layouts;
- history graphs;
- automatic room/Space provisioning;
- automatic Widget state-event installation across more Matrix clients;
- optional sticky-event optimization when MSC support is mature;
- broader Matrix client compatibility beyond the tested Element path.
