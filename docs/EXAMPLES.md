# Practical Matrix Extended examples

**English** · [Русский](EXAMPLES.ru.md)

These are complete YAML patterns for Home Assistant Developer Tools → Actions, scripts, and automations. Replace sample rooms, users, and entity IDs with your own values.

## 1. `matrix_extended.send` — general send

### Simple text to the default room

```yaml
action: matrix_extended.send
data:
  message: "Home Assistant is online"
```

### Markdown + notice + native mention

```yaml
action: matrix_extended.send
data:
  target:
    - "#security:example.org"
  format: markdown
  msgtype: notice
  message: "**Alarm:** garage door is open"
  mention_users:
    - "@seriy:example.org"
```

### Update one Matrix event instead of sending new messages

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "backup.nightly"
  message: "Nightly backup — 25%"
```

Call it again with the same `notification_key` and a different message; Matrix Extended edits the original event.

### Camera + one-shot safe reaction action

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Motion at the gate. React with 💡 to turn on the light."
  media:
    - entity_id: camera.gate
      caption: "Latest frame"
  actions:
    - reaction: "💡"
      service: light.turn_on
      target:
        entity_id: light.gate
      expires_in: 300
      max_uses: 1
      allowed_users:
        - "@seriy:example.org"
```

Incoming Matrix content cannot replace `light.turn_on`, its target, or data.

### Capture the sent Matrix event ID

```yaml
action: matrix_extended.send
response_variable: mx_send
data:
  message: "A message we will edit later"

# When status=sent, mx_send.events[0].event_id is the Matrix event ID.
```

When `status: queued`, `events` may be empty until delivery; correlate `matrix_extended_delivery` with `delivery_id`.

## 2. `matrix_extended.send_media` — Media Browser

The normal workflow is to select the item graphically in **Choose media**. If you switch the action to YAML, the selector looks approximately like this:

```yaml
action: matrix_extended.send_media
data:
  media_picker:
    media_content_id: "media-source://media_source/local/example.mp4"
    media_content_type: video/mp4
  caption: "Video from Home Assistant Media Browser"
```

Do not invent `media_content_id`; let Home Assistant populate it through the Media Browser.

### Send selected audio as native Matrix voice

```yaml
action: matrix_extended.send_media
data:
  target:
    - "!room:example.org"
  media_picker:
    media_content_id: "media-source://media_source/local/voice.ogg"
    media_content_type: audio/ogg
  voice: true
  caption: "Voice message"
```

Protected HA Media Source providers use a temporary signed URL. Starting with v0.5.6, Frigate VOD is also converted to the HA MP4 recording proxy before Matrix upload.

## 3. `matrix_extended.send_voice` — TTS → Matrix voice

### Use the default Home Assistant TTS provider

```yaml
action: matrix_extended.send_voice
data:
  text: "Attention. The garage door has been open for ten minutes."
  language: en
```

### Select a TTS entity and capture delivery response

```yaml
action: matrix_extended.send_voice
response_variable: voice_send
data:
  route: security
  text: "Garage temperature is {{ states('sensor.garage_temperature') }} degrees"
  tts_engine: tts.piper
  language: en-US

# voice_send.status: sent / queued / failed / dropped
```

Use `tts_options` only according to the selected TTS provider's own options.

## 4. `matrix_extended.transcribe_voice` — Matrix voice → STT/Assist

Matrix Extended stores incoming media per account under:

`/config/matrix_extended/incoming/<config_entry_id>/`

Normally you never construct the path yourself. `matrix_extended_media` already contains `local_path`.

### Working pattern: voice → STT → notification

```yaml
alias: Matrix voice to STT
triggers:
  - trigger: event
    event_type: matrix_extended_media
conditions:
  - condition: template
    value_template: >-
      {{
        (trigger.event.data.voice | default(false) | bool)
        and ((trigger.event.data.local_path | default('')) | length > 0)
        and (trigger.event.data.download_error is none)
      }}
actions:
  - action: matrix_extended.transcribe_voice
    response_variable: voice_result
    data:
      path: "{{ trigger.event.data.local_path }}"
      stt_entity: stt.faster_whisper
      language: en
  - action: persistent_notification.create
    data:
      title: Matrix voice
      message: "{{ voice_result.text }}"
mode: single
```

Avoid a condition that simply returns `voice and local_path`: Jinja can return the path string rather than an explicit boolean.

### Voice → STT → Home Assistant Assist

Only enable this for trusted sender/room allowlists.

```yaml
alias: Matrix voice to Assist
triggers:
  - trigger: event
    event_type: matrix_extended_media
conditions:
  - condition: template
    value_template: >-
      {{
        (trigger.event.data.voice | default(false) | bool)
        and ((trigger.event.data.local_path | default('')) | length > 0)
        and (trigger.event.data.download_error is none)
      }}
actions:
  - action: matrix_extended.transcribe_voice
    response_variable: voice_result
    data:
      path: "{{ trigger.event.data.local_path }}"
      stt_entity: stt.faster_whisper
      language: en
      assist: true
      conversation_agent: conversation.home_assistant
  - action: matrix_extended.reply
    data:
      room: "{{ trigger.event.data.room_id }}"
      event_id: "{{ trigger.event.data.event_id }}"
      message: "Transcript: {{ voice_result.text }}"
mode: queued
```

### Manual STT test

Copy a real `local_path` from a `matrix_extended_media` event:

```yaml
action: matrix_extended.transcribe_voice
response_variable: voice_result
data:
  path: "/config/matrix_extended/incoming/0123456789abcdef/abc123456789-Voice message"
  stt_entity: stt.faster_whisper
  language: en
```

The response includes `text`, `stt_entity`, `language`, `normalized`, `assist_executed`, and optionally `assist`.

## 5. `matrix_extended.send_location` — location

### Mode 1: coordinates from an entity

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  entity_id: person.seriy
  description: "Current position"
```

The entity must expose `latitude` and `longitude` attributes.

### Mode 2: explicit coordinates

```yaml
action: matrix_extended.send_location
data:
  route: family
  latitude: 40.7128
  longitude: -74.0060
  description: "Meeting point"
```

Do not combine `entity_id` with explicit coordinates.

## 6. `matrix_extended.reply` — reply to an incoming event

### Reply to `ping` in the same room

```yaml
alias: Matrix ping reply
triggers:
  - trigger: event
    event_type: matrix_extended_message
conditions:
  - condition: template
    value_template: >-
      {{ (trigger.event.data.body | default('') | lower) == 'ping' }}
actions:
  - action: matrix_extended.reply
    data:
      room: "{{ trigger.event.data.room_id }}"
      event_id: "{{ trigger.event.data.event_id }}"
      message: "pong"
mode: queued
```

### Markdown reply with mention

```yaml
action: matrix_extended.reply
data:
  room: "!room:example.org"
  event_id: "$original_event_id"
  format: markdown
  message: "**Done:** task completed"
  mention_users:
    - "@seriy:example.org"
```

## 7. `matrix_extended.react` — reaction

```yaml
alias: Matrix acknowledge
triggers:
  - trigger: event
    event_type: matrix_extended_message
actions:
  - action: matrix_extended.react
    data:
      room: "{{ trigger.event.data.room_id }}"
      event_id: "{{ trigger.event.data.event_id }}"
      reaction: "✅"
mode: queued
```

With matrix-nio 0.26.0, the `m.reaction` event itself is not encrypted.

## 8. `matrix_extended.edit` — edit a message

```yaml
sequence:
  - action: matrix_extended.send
    response_variable: mx_send
    data:
      message: "Starting task…"
  - delay: "00:00:05"
  - condition: template
    value_template: >-
      {{ mx_send.status == 'sent' and (mx_send.events | count) > 0 }}
  - action: matrix_extended.edit
    data:
      room: "{{ mx_send.events[0].room_id }}"
      event_id: "{{ mx_send.events[0].event_id }}"
      message: "Task complete"
```

For repeated status updates without keeping an event ID, prefer `notification_key` in `matrix_extended.send`.

## 9. `matrix_extended.redact` — redaction

```yaml
action: matrix_extended.redact
data:
  room: "!room:example.org"
  event_id: "$event_to_redact"
  reason: "Removed by Home Assistant automation"
```

This is Matrix redaction on the homeserver, not deletion of Home Assistant logbook/event data.

## 10. `matrix_extended.purge_media` — incoming-media cleanup

### Manual cleanup with response

```yaml
action: matrix_extended.purge_media
response_variable: purge_result
```

Response values are available as:

```jinja2
{{ purge_result.removed_files }}
{{ purge_result.removed_bytes }}
```

### Weekly cleanup with notification

```yaml
alias: Matrix incoming media cleanup
triggers:
  - trigger: time
    at: "04:30:00"
conditions:
  - condition: time
    weekday:
      - sun
actions:
  - action: matrix_extended.purge_media
    response_variable: purge_result
  - action: persistent_notification.create
    data:
      title: Matrix cleanup
      message: >-
        Removed files: {{ purge_result.removed_files }},
        bytes: {{ purge_result.removed_bytes }}
mode: single
```

## 11. `matrix_extended.register_command` — safe commands

Matrix commands are matched only when the incoming message starts with `!`. Register `trigger`/`aliases` without `!`; matching is case-insensitive and normalizes extra whitespace.

### Mode 1: fixed Home Assistant service

```yaml
action: matrix_extended.register_command
response_variable: command_result
data:
  id: garage_light_on
  trigger: "garage light on"
  aliases:
    - "light garage"
  description: "Turn on garage light"
  allowed_users:
    - "@seriy:example.org"
  allowed_rooms:
    - "!garage_room:example.org"
  progress: true
  handler_type: service
  service: light.turn_on
  target:
    entity_id: light.garage
  data:
    brightness_pct: 100
```

The Matrix user then sends:

```text
!garage light on
```

Incoming text selects the stored command but cannot provide a different service or entity.

### Mode 2: camera snapshot

```yaml
action: matrix_extended.register_command
data:
  id: gate_camera
  trigger: "gate camera"
  description: "Get gate camera snapshot"
  allowed_users:
    - "@seriy:example.org"
  progress: true
  handler_type: camera_snapshot
  entity_id: camera.gate
  caption: "Gate camera"
```

Matrix command:

```text
!gate camera
```

Do not specify `service`, `target`, or `data` for a `camera_snapshot` handler.

## 12. `matrix_extended.unregister_command` — remove a command

```yaml
action: matrix_extended.unregister_command
response_variable: remove_result
data:
  id: garage_light_on
```

Response:

```jinja2
ID: {{ remove_result.id }}
Removed: {{ remove_result.removed }}
```

`removed: false` means the ID was already absent.

## 13. `matrix_extended_delivery` — queue/error monitoring

This is an event rather than an action, but it is useful for outbound automations.

```yaml
alias: Matrix delivery problems
triggers:
  - trigger: event
    event_type: matrix_extended_delivery
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.status in ['queued', 'failed', 'dropped'] }}
actions:
  - action: system_log.write
    data:
      level: warning
      message: >-
        Matrix delivery {{ trigger.event.data.delivery_id }}:
        {{ trigger.event.data.status }}
        {{ trigger.event.data.error | default('') }}
mode: queued
```

## 14. Send inside a Matrix thread

```yaml
action: matrix_extended.send
data:
  target:
    - "!room:example.org"
  message: "Update inside the thread"
  thread_id: "$thread_root_event"
```

`send` uses `target` because it can address multiple rooms. `reply` uses the single-room `room` field.

## 15. Native Matrix control panels (`0.6.0b1`)

These snippets are **panel YAML import definitions**, not `matrix_extended.*` service calls. Create them graphically under Matrix Extended → Configure → Native Matrix control panels, or import one validated document. See [Native Matrix control panels](CONTROL_PANELS.md).

### Garage — dangerous action with confirmation

```yaml
panel_id: garage
room_id: "!garage:example.org"
title: Garage
enabled: true
entities:
  - entity_id: cover.garage
    label: Garage door
actions:
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

`confirmation_required: true` means the first reaction only creates a confirmation request. The same Matrix sender must answer with `✅` within 30 seconds before `cover.open_cover` runs.

### Alarm — dangerous disarm action

```yaml
panel_id: alarm
room_id: "!security:example.org"
title: Security
enabled: true
entities:
  - entity_id: alarm_control_panel.home
    label: Alarm
actions:
  - id: alarm_disarm
    reaction: "🛑"
    label: Disarm alarm
    service: alarm_control_panel.alarm_disarm
    target:
      entity_id: alarm_control_panel.home
    data: {}
    confirmation_required: true
allowed_users:
  - "@owner:example.org"
debounce: 1.0
```

If your alarm provider requires sensitive service data, keep it local and treat exported panel YAML as sensitive configuration.

### Light and climate — low-risk one-step actions

```yaml
panel_id: living
room_id: "!living:example.org"
title: Living room
enabled: true
entities:
  - entity_id: light.living_room
    label: Light
  - entity_id: climate.living_room
    label: Climate
actions:
  - id: light_toggle
    reaction: "💡"
    label: Toggle light
    service: light.toggle
    target:
      entity_id: light.living_room
    data: {}
    confirmation_required: false
  - id: climate_comfort
    reaction: "🌡️"
    label: Set 21 °C
    service: climate.set_temperature
    target:
      entity_id: climate.living_room
    data:
      temperature: 21
    confirmation_required: false
allowed_users: []
debounce: 1.5
```

`allowed_users: []` does not make the panel public: it means there is no *additional* panel restriction, so the account-level sender and room allowlists still apply.

## Maps in self-hosted Element

`matrix_extended.send_location` sends standard `m.location`. A tile server is not required to send the event. To render the map in Element Web, configure the map/tile style on the Element/homeserver side.
