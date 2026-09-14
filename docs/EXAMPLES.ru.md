# Практические примеры

[English](EXAMPLES.md) · **Русский**

В редакторе действий Home Assistant уже есть описания полей. Здесь собраны законченные шаблоны автоматизаций, которые можно брать за основу.

## 1. Снимок с камеры + одноразовое действие по реакции

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

Можно вызвать только то действие Home Assistant, которое было привязано к конкретному исходящему событию. Произвольный текст из Matrix никогда не выполняется как YAML/Jinja Home Assistant.

## 2. Отправить текущее положение человека

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  entity_id: person.seriy
  description: "Current position"
```

У сущности должны быть атрибуты `latitude` и `longitude`.

## 3. TTS → нативное голосовое сообщение Matrix

```yaml
action: matrix_extended.send_voice
data:
  route: security
  text: "Attention. The garage door has been open for ten minutes."
  language: en-US
```

Указывайте `tts_engine` только если нужен конкретный TTS-провайдер Home Assistant.

## 4. Входящее голосовое Matrix → STT

Запускайте автоматизацию по скачанному входящему Matrix-медиа и распознавайте только голосовые сообщения:

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

Добавляйте `assist: true` только для явно доверенных allowlist пользователей и комнат.

## 5. Отслеживать queued/sent/failed доставку

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

## 6. Обновлять одно Matrix-сообщение вместо отправки новых

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "backup.nightly"
  message: "Nightly backup — 25%"
```

Отправьте действие повторно с тем же `notification_key`; Matrix Extended отредактирует существующее Matrix-событие через `m.replace`.

## 7. Markdown + нативное Matrix-упоминание

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

## Карта в self-hosted Element

`matrix_extended.send_location` отправляет стандартный `m.location`. Для самой отправки tile server не требуется. Чтобы Element Web нарисовал карту, настройте map/tile style на стороне Element/homeserver. CI использует OpenFreeMap только для одноразового showcase-клиента.
