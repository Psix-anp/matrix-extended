# Matrix Extended Roadmap

This roadmap records candidate work beyond the current 0.5.x release line. Items are not part of the 0.5.1 release contract unless explicitly moved into its design/spec.

## 0.6.0 direction — advanced Home Assistant integration over Matrix

Matrix Extended remains a Home Assistant integration. Matrix/Element are the transport and user interface; Home Assistant remains the control, entity, Assist, media and automation runtime.

Current leading candidates:

- Matrix threads mapped to persistent Home Assistant conversation IDs for multi-turn Assist sessions.
- Structured safe query handlers that return Home Assistant action/service response data to Matrix.
- Live/updateable status messages built from the existing edit and notification-key mechanisms.
- Unified safe actions so registered operations can be invoked by exact commands, reaction actions and Assist without exposing arbitrary runtime services/entities.
- Home Assistant UI/Options Flow management for registered safe commands and handlers.
- Richer camera flows around snapshots and registered follow-up actions.
- Typing/read-receipt UX and expanded delivery/E2EE/command diagnostics where supported safely.

## 0.6.x candidate — inline camera / Frigate video clips

Approved direction: support finished event clips that play directly inside Element as Matrix `m.video` messages.

Expected flow:

1. Home Assistant or Frigate exposes a completed local/event clip.
2. Matrix Extended resolves the clip through an integration-owned or Home Assistant-controlled media path/API.
3. The integration sends it through the existing Matrix media pipeline as `m.video`.
4. Include useful metadata when available: MIME type, size, duration, dimensions and thumbnail.
5. Preserve the existing E2EE behavior for encrypted rooms.
6. Element renders the clip inline with its normal video player.

Initial compatibility target should favor broadly playable MP4/H.264 + AAC output when transcoding/normalization is required or already available through Home Assistant/Frigate.

The first implementation is deliberately **clip-only**. Matrix Extended will not become an RTSP/HLS proxy and will not introduce a separate streaming server merely to provide live video.

Potential user flows:

- Frigate person/vehicle event -> Matrix notification -> inline event clip.
- Safe command or camera handler -> latest event clip for a registered camera.
- Snapshot + inline clip + registered reaction actions in one notification flow.

## Later candidates

- Live Matrix location/beacons mapped to Home Assistant `person` / `device_tracker` state where protocol/client support is sufficiently stable.
- Matrix Spaces-aware routing/grouping.
- Deeper E2EE device/key diagnostics as upstream matrix-nio capabilities mature.
- Polls/approvals only when their Matrix protocol/client support is stable enough to justify replacing existing reaction actions.

## Guardrails

- No separate Matrix Extended backend/daemon solely for future features.
- No arbitrary Matrix text selecting Home Assistant service names, entity IDs, YAML, Jinja, shell commands or Python expressions.
- Prefer existing Home Assistant APIs and the existing Matrix Extended media, E2EE, outbox, delivery, reply/edit and Assist infrastructure.
- Keep optional advanced capabilities fail-closed and disabled by default where execution or privacy risk is involved.
