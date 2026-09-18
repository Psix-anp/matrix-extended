# Практические примеры Matrix Extended

[English](EXAMPLES.md) · **Русский**

Ниже — законченные YAML-шаблоны, которые можно копировать в Developer Tools → Actions, скрипты и автоматизации Home Assistant. Замените примеры комнат, пользователей и entity ID на свои.

## 1. `matrix_extended.send` — основная отправка

### Простой текст в комнату по умолчанию

```yaml
action: matrix_extended.send
data:
  message: "Home Assistant работает"
```

### Markdown + notice + нативное упоминание

```yaml
action: matrix_extended.send
data:
  target:
    - "#security:example.org"
  format: markdown
  msgtype: notice
  message: "**Тревога:** дверь гаража открыта"
  mention_users:
    - "@seriy:example.org"
```

### Обновляемое сообщение вместо спама новыми сообщениями

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "backup.nightly"
  message: "Ночной backup — 25%"
```

Позже вызовите то же действие с тем же `notification_key` и новым `message`, например `Ночной backup — 80%`. Matrix Extended отредактирует исходное событие.

### Камера + безопасное одноразовое действие по реакции

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Движение у ворот. Нажми 💡, чтобы включить свет."
  media:
    - entity_id: camera.gate
      caption: "Последний кадр"
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

Входящий Matrix-текст не может заменить `light.turn_on`, target или data.

### Получить `event_id` отправленного сообщения

```yaml
action: matrix_extended.send
response_variable: mx_send
data:
  message: "Сообщение, которое потом можно изменить"

# mx_send.events[0].event_id содержит Matrix event ID при status=sent.
```

Если `status: queued`, список `events` может быть пуст до фактической доставки; следите за `matrix_extended_delivery` по `delivery_id`.

## 2. `matrix_extended.send_media` — Media Browser

Для обычной автоматизации проще выбрать файл графически через поле **Выбрать медиа**. После переключения действия в YAML selector выглядит примерно так:

```yaml
action: matrix_extended.send_media
data:
  media_picker:
    media_content_id: "media-source://media_source/local/example.mp4"
    media_content_type: video/mp4
  caption: "Видео из Home Assistant Media Browser"
```

`media_content_id` не нужно придумывать вручную — выберите элемент в GUI и Home Assistant заполнит объект.

### Отправить выбранное аудио как нативное voice

```yaml
action: matrix_extended.send_media
data:
  target:
    - "!room:example.org"
  media_picker:
    media_content_id: "media-source://media_source/local/voice.ogg"
    media_content_type: audio/ogg
  voice: true
  caption: "Голосовое сообщение"
```

Frigate и другие protected Home Assistant Media Source providers используют временно подписанный внутренний URL; в v0.5.6 Frigate VOD также преобразуется в MP4 recording proxy перед Matrix upload.

## 3. `matrix_extended.send_voice` — TTS → Matrix voice

### Использовать TTS Home Assistant по умолчанию

```yaml
action: matrix_extended.send_voice
data:
  text: "Внимание. Ворота гаража открыты десять минут."
  language: ru
```

### Явно выбрать TTS entity и получить delivery response

```yaml
action: matrix_extended.send_voice
response_variable: voice_send
data:
  route: security
  text: "Температура в гараже {{ states('sensor.garage_temperature') }} градусов"
  tts_engine: tts.piper
  language: ru-RU

# voice_send.status: sent / queued / failed / dropped
```

`tts_options` задавайте только по документации конкретного TTS provider, например если он поддерживает выбор голоса.

## 4. `matrix_extended.transcribe_voice` — Matrix voice → STT/Assist

Matrix Extended сохраняет входящие медиа каждого аккаунта в:

`/config/matrix_extended/incoming/<config_entry_id>/`

Нормально вручную путь не составлять: событие `matrix_extended_media` уже содержит `local_path`.

### Рабочая автоматизация: voice → Faster Whisper → уведомление

Этот вариант подтверждён реальным trace Home Assistant.

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
      language: ru
  - action: persistent_notification.create
    data:
      title: Matrix voice
      message: "{{ voice_result.text }}"
mode: single
```

Не используйте условие вида `voice and local_path` без явной проверки длины: результатом такого Jinja-выражения может стать строка, а condition должен возвращать boolean.

### Voice → STT → Home Assistant Assist

Используйте только для доверенных sender/room allowlists.

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
      language: ru
      assist: true
      conversation_agent: conversation.home_assistant
  - action: matrix_extended.reply
    data:
      room: "{{ trigger.event.data.room_id }}"
      event_id: "{{ trigger.event.data.event_id }}"
      message: >-
        Распознано: {{ voice_result.text }}
        {% if voice_result.assist is defined %}
        Assist выполнен.
        {% endif %}
mode: queued
```

### Ручной тест STT

Скопируйте реальный `local_path` из события `matrix_extended_media`:

```yaml
action: matrix_extended.transcribe_voice
response_variable: voice_result
data:
  path: "/config/matrix_extended/incoming/0123456789abcdef/abc123456789-Voice message"
  stt_entity: stt.faster_whisper
  language: ru
```

Ответ содержит `text`, `stt_entity`, `language`, `normalized`, `assist_executed`, а при Assist ещё и `assist`.

## 5. `matrix_extended.send_location` — геопозиция

### Режим 1: координаты из entity

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  entity_id: person.seriy
  description: "Текущее положение"
```

У entity должны быть атрибуты `latitude` и `longitude`.

### Режим 2: явные координаты

```yaml
action: matrix_extended.send_location
data:
  route: family
  latitude: 55.7558
  longitude: 37.6173
  description: "Точка встречи"
```

Не указывайте `entity_id` одновременно с координатами.

## 6. `matrix_extended.reply` — ответ на входящее сообщение

### Автоматически ответить отправителю в той же комнате

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

### Reply с Markdown и mention

```yaml
action: matrix_extended.reply
data:
  room: "!room:example.org"
  event_id: "$original_event_id"
  format: markdown
  message: "**Готово:** задача завершена"
  mention_users:
    - "@seriy:example.org"
```

## 7. `matrix_extended.react` — реакция

### Поставить ✅ на входящее сообщение

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

Помните: в matrix-nio 0.26.0 само `m.reaction` не шифруется.

## 8. `matrix_extended.edit` — редактирование

### Отправить сообщение, подождать и изменить его по event ID

```yaml
sequence:
  - action: matrix_extended.send
    response_variable: mx_send
    data:
      message: "Запуск задачи…"
  - delay: "00:00:05"
  - condition: template
    value_template: >-
      {{ mx_send.status == 'sent' and (mx_send.events | count) > 0 }}
  - action: matrix_extended.edit
    data:
      room: "{{ mx_send.events[0].room_id }}"
      event_id: "{{ mx_send.events[0].event_id }}"
      message: "Задача завершена"
```

Если нужно часто обновлять один статус без хранения event ID, используйте `notification_key` в `matrix_extended.send`.

## 9. `matrix_extended.redact` — redaction

```yaml
action: matrix_extended.redact
data:
  room: "!room:example.org"
  event_id: "$event_to_redact"
  reason: "Удалено автоматизацией Home Assistant"
```

Это Matrix redaction на homeserver, а не удаление Home Assistant logbook/event.

## 10. `matrix_extended.purge_media` — очистка входящих медиа

### Ручная очистка с результатом

```yaml
action: matrix_extended.purge_media
response_variable: purge_result
data: {}
```

После выполнения доступны:

```jinja2
{{ purge_result.removed_files }}
{{ purge_result.removed_bytes }}
```

### Еженедельная очистка с уведомлением

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
        Удалено файлов: {{ purge_result.removed_files }},
        байт: {{ purge_result.removed_bytes }}
mode: single
```

## 11. `matrix_extended.register_command` — безопасные команды

Команды выполняются только если в Matrix сообщение начинается с `!`. `trigger` и `aliases` при регистрации задаются без `!`; регистр не важен, лишние пробелы нормализуются.

### Режим 1: фиксированный Home Assistant service

```yaml
action: matrix_extended.register_command
response_variable: command_result
data:
  id: garage_light_on
  trigger: "garage light on"
  aliases:
    - "гараж свет"
    - "light garage"
  description: "Включить свет в гараже"
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

После регистрации пользователь отправляет в разрешённой комнате:

```text
!garage light on
```

или, например:

```text
!гараж свет
```

Matrix-сообщение выбирает только сохранённую команду и не может передать другой `entity_id` или service.

### Режим 2: снимок камеры

```yaml
action: matrix_extended.register_command
data:
  id: gate_camera
  trigger: "gate camera"
  aliases:
    - "ворота камера"
  description: "Получить снимок камеры ворот"
  allowed_users:
    - "@seriy:example.org"
  progress: true
  handler_type: camera_snapshot
  entity_id: camera.gate
  caption: "Камера ворот"
```

Команда в Matrix:

```text
!gate camera
```

Для `camera_snapshot` не задавайте `service`, `target` или `data`.

## 12. `matrix_extended.unregister_command` — удаление команды

```yaml
action: matrix_extended.unregister_command
response_variable: remove_result
data:
  id: garage_light_on
```

Результат:

```jinja2
ID: {{ remove_result.id }}
Удалено: {{ remove_result.removed }}
```

`removed: false` означает, что команды с таким ID не было.

## 13. Событие `matrix_extended_delivery` — контроль очереди и ошибок

Это не action, но полезно почти для всех исходящих автоматизаций.

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

## 14. Thread: отправка внутри ветки

```yaml
action: matrix_extended.send
data:
  target:
    - "!room:example.org"
  message: "Обновление внутри ветки"
  thread_id: "$thread_root_event"
```

У `send` поле комнаты называется `target`, потому что действие может отправлять сразу в несколько комнат. У `reply` используется `room`, потому что reply адресуется одной Matrix room.

## 15. Нативные панели управления Matrix (`0.6.0b1`)

Следующие блоки — **YAML определения панелей для import**, а не вызовы `matrix_extended.*`. Панель можно собрать графически через Matrix Extended → Настроить → Нативные панели управления Matrix или импортировать один валидированный YAML document. Подробности: [Нативные панели управления Matrix](CONTROL_PANELS.ru.md).

### Гараж — опасное действие с подтверждением

```yaml
panel_id: garage
room_id: "!garage:example.org"
title: Гараж
enabled: true
entities:
  - entity_id: cover.garage
    label: Ворота гаража
actions:
  - id: garage_open
    reaction: "🔓"
    label: Открыть гараж
    service: cover.open_cover
    target:
      entity_id: cover.garage
    data: {}
    confirmation_required: true
allowed_users:
  - "@owner:example.org"
debounce: 1.5
```

`confirmation_required: true` означает, что первая реакция только создаёт запрос подтверждения. Тот же Matrix sender обязан нажать `✅` в течение 30 секунд, и только после этого выполняется `cover.open_cover`.

### Сигнализация — опасное снятие с охраны

```yaml
panel_id: alarm
room_id: "!security:example.org"
title: Охрана
enabled: true
entities:
  - entity_id: alarm_control_panel.home
    label: Сигнализация
actions:
  - id: alarm_disarm
    reaction: "🛑"
    label: Снять с охраны
    service: alarm_control_panel.alarm_disarm
    target:
      entity_id: alarm_control_panel.home
    data: {}
    confirmation_required: true
allowed_users:
  - "@owner:example.org"
debounce: 1.0
```

Если ваш alarm provider требует чувствительные service data, храните их только локально и считайте экспортированный panel YAML чувствительной конфигурацией.

### Свет и климат — обычные одноступенчатые действия

```yaml
panel_id: living
room_id: "!living:example.org"
title: Гостиная
enabled: true
entities:
  - entity_id: light.living_room
    label: Свет
  - entity_id: climate.living_room
    label: Климат
actions:
  - id: light_toggle
    reaction: "💡"
    label: Переключить свет
    service: light.toggle
    target:
      entity_id: light.living_room
    data: {}
    confirmation_required: false
  - id: climate_comfort
    reaction: "🌡️"
    label: Установить 21 °C
    service: climate.set_temperature
    target:
      entity_id: climate.living_room
    data:
      temperature: 21
    confirmation_required: false
allowed_users: []
debounce: 1.5
```

`allowed_users: []` не делает панель публичной: это только отсутствие дополнительного panel-level ограничения. Account-level allowlist отправителей и комнат продолжает действовать.

## Карта в self-hosted Element

`matrix_extended.send_location` отправляет стандартный `m.location`. Для самой отправки tile server не нужен. Чтобы Element Web отрисовал карту, настройте map/tile style на стороне Element/homeserver.
