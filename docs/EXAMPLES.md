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

When incoming-media downloads are enabled, Matrix Extended stores received voice files under:

`/config/matrix_extended/incoming/<config_entry_id>/`

The `matrix_extended_media` event exposes the exact full path as `local_path`, so automations do not need to construct the filename or config-entry ID manually.

Automation for native Matrix voice messages only:

```yaml
trigger:
  - platform: event
    event_type: matrix_extended_media
condition:
  - condition: template
    value_template: >-
      {{ trigger.event.data.voice | default(false)
         and trigger.event.data.local_path | default('') }}
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
      message: "{{ voice_result.text }}"
```

`matrix_extended.transcribe_voice` returns at least `text`, `stt_entity`, `language`, `normalized`, and `assist_executed`. When `assist: true` is used, the response also contains `assist`.

For a manual Developer Tools → Actions test, copy `local_path` from a `matrix_extended_media` event and call:

```yaml
action: matrix_extended.transcribe_voice
data:
  path: "/config/matrix_extended/incoming/0123456789abcdef/abc123456789-voice-message.ogg"
  stt_entity: stt.whisper
  language: ru
```

The path above is only an example. The action intentionally refuses arbitrary files outside the selected Matrix account's incoming-media directory.

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