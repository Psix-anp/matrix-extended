# Practical examples

**English** · [Русский](EXAMPLES.ru.md)

The service/action editor in Home Assistant contains field descriptions. These examples focus on complete automation patterns.

## 1. Camera snapshot + one-shot reaction action

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Motion at the gate"
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

Only the service attached by Home Assistant to that outgoing event can be invoked; arbitrary Matrix text is never executed as HA YAML/Jinja.

## 2. Send a person's current position

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  entity_id: person.seriy
  description: "Current position"
```

The entity must expose `latitude` and `longitude` attributes.

## 3. TTS → native Matrix voice

```yaml
action: matrix_extended.send_voice
data:
  route: security
  text: "Attention. The garage door has been open for ten minutes."
  language: en-US
```

Set `tts_engine` only when you need a specific Home Assistant TTS provider.

## 4. Incoming Matrix voice → STT

Trigger on downloaded incoming Matrix media and transcribe only voice messages:

```yaml
trigger:
  - platform: event
    event_type: matrix_extended_media
condition:
  - condition: template
    value_template: "{{ trigger.event.data.voice | default(false) }}"
action:
  - action: matrix_extended.transcribe_voice
    response_variable: voice_result
    data:
      path: "{{ trigger.event.data.local_path }}"
      stt_entity: stt.whisper
      language: ru
  - action: persistent_notification.create
    data:
      title: "Matrix voice"
      message: "{{ voice_result.transcript }}"
```

Add `assist: true` only for explicitly trusted user/room allowlists.

## 5. Track queued/sent/failed delivery

```yaml
trigger:
  - platform: event
    event_type: matrix_extended_delivery
condition:
  - condition: template
    value_template: "{{ trigger.event.data.status in ['queued', 'failed', 'dropped'] }}"
action:
  - action: system_log.write
    data:
      level: warning
      message: >-
        Matrix delivery {{ trigger.event.data.delivery_id }}:
        {{ trigger.event.data.status }}
```

## 6. Update one Matrix message instead of sending many

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "backup.nightly"
  message: "Nightly backup — 25%"
```

Send again with the same `notification_key`; Matrix Extended edits the existing Matrix event with `m.replace`.

## 7. Markdown + native Matrix mention

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

## Maps in self-hosted Element

`matrix_extended.send_location` sends standard `m.location`. A tile server is not required to send the event itself. To render a map in Element Web, configure the map/tile style on the Element/homeserver side. CI uses OpenFreeMap only for the disposable showcase client.
