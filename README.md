# Matrix Extended for Home Assistant

`matrix_extended` — компактная кастомная интеграция Home Assistant для Matrix с E2EE, rich media и двусторонним управлением.

Версия `0.4.2` ориентирована на Home Assistant 2026.9+ и использует `matrix-nio==0.26.0` с явно закреплёнными E2EE-зависимостями (`atomicwrites`, `cachetools`, `peewee`, `vodozemac`). Релиз проверяется на реальном Home Assistant 2026.9.2 + Synapse 1.160.0 перед merge/publish.

## Что есть в v0.4.x

- Config Flow; пароль используется только для первичного login и не сохраняется.
- Постоянный Matrix E2EE crypto-store между перезапусками HA.
- `Require E2EE` по умолчанию блокирует отправку в незашифрованные комнаты.
- Текст, фото, видео, audio, файлы и thumbnails с E2EE.
- `camera.*`, `image.*`, локальный `path`, URL и `media-source://`.
- `matrix_extended.send` + стандартная `notify` entity.
- Threads.
- **Rich replies**: `matrix_extended.reply`.
- **Reactions**: `matrix_extended.react`.
- **Edit** (`m.replace`): `matrix_extended.edit`.
- **Redact**: `matrix_extended.redact`.
- Live sync входящих сообщений с E2EE-decryption.
- Входящие HA events: `matrix_extended_message`, `matrix_extended_reply`, `matrix_extended_reaction`, `matrix_extended_media`.
- Входящие encrypted attachments скачиваются и расшифровываются локально в HA.
- Allowlist пользователей **и** комнат: входящее событие принимается только при совпадении обоих.
- Reaction actions: реакция может однократно вызвать только тот HA service, который HA сам заранее прикрепил к конкретному исходящему сообщению.
- Никакого выполнения произвольного service/YAML/Jinja из текста Matrix.
- Диагностика: connection, user/device/default room/E2EE, last send, last incoming, last error.
- Автоматическое обнаружение joined rooms после полного Matrix sync.
- Отдельная `notify` entity для каждой joined room + общая notify entity для комнаты по умолчанию.
- `select` для выбора default room прямо из Home Assistant.
- Именованные routing profiles (`security`, `system`, `family` и т. п.).
- `notification_key`: первое сообщение создаётся, последующие с тем же ключом редактируют исходный Matrix event (`m.replace`) вместо спама.
- Соответствия `notification_key -> room -> event_id` сохраняются в `.storage` и переживают перезапуск HA.
- Автоматическое восстановление live sync после недоступности homeserver; диагностика переключается `off/on` вместе с фактическим соединением.

## E2EE

TLS и Matrix E2EE — разные уровни. Для encrypted room `matrix-nio` шифрует `m.room.message` через Megolm. Media шифруется до upload и отправляется через Matrix `file` / `thumbnail_file`; homeserver получает ciphertext.

Crypto-store:

```text
/config/.storage/matrix_extended/<config_entry_id>/
```

Updateable notification mappings хранятся отдельно через Home Assistant Store (`matrix_extended.notification_keys_<config_entry_id>`). В файле нет Matrix access token или media content — только notification key, room ID и event ID.

В `0.4.2` E2EE runtime-зависимости объявлены явно, чтобы встроенная Matrix-интеграция Home Assistant с уже установленным базовым `matrix-nio` не могла оставить кастомную интеграцию без crypto-зависимостей. Загрузка persistent crypto-store также вынесена из event loop Home Assistant.

`matrix-nio 0.26.0` пока не поддерживает cross-signing. Также в этой версии upstream есть проблема SAS verification с Element. Поэтому содержимое E2EE защищено от homeserver, но строгая политика «ключи только вручную verified devices» пока не реализована.

**Важно:** `matrix-nio 0.26.0` специально не шифрует `m.reaction`, поэтому emoji и связь реакции с событием видны homeserver. Не используйте реакцию для PIN/паролей/секретов.

## Установка / обновление

Скопируйте:

```text
custom_components/matrix_extended
```

в:

```text
/config/custom_components/matrix_extended
```

Перезапустите HA. При обновлении с v0.2/v0.3/v0.4.1 config entry, access token и crypto-store сохраняются. Новые routing/notification настройки имеют безопасные значения по умолчанию.

## Входящие: настройка безопасности

После установки откройте **Настройки → Устройства и службы → Matrix Extended → Настроить**.

Параметры:

- `Incoming enabled` — live sync входящих событий;
- `Allowed users` — Matrix IDs, например `@seriy:example.org`;
- `Allowed rooms` — room alias/ID;
- `Download incoming media` — скачать и расшифровать вложение локально;
- `Require E2EE` — запрет исходящей отправки в plaintext-комнаты.

Если allowlist не задан при первичной установке, безопасный default: текущий Matrix user + default room. Для отдельного bot-account добавьте свой пользовательский Matrix ID в `Allowed users`.

Входящие файлы сохраняются в:

```text
/config/matrix_extended/incoming/<config_entry_id>/
```

Лимит входящего файла: 32 MiB. Исходящего: 128 MiB.

## Обычная отправка

```yaml
action: matrix_extended.send
data:
  target:
    - "#security:example.org"
  message: "Движение у ворот"
  media:
    - entity_id: camera.gate
      caption: "Свежий кадр"
```

## Комнаты и notify entities

После initial full sync интеграция создаёт:

- одну общую `notify` entity — отправляет в текущую default room;
- отдельную `notify` entity для каждой joined room;
- `select` **Default room**, где видны человекочитаемые названия комнат.

У room-specific notify entity в атрибутах есть `room_id`, `canonical_alias`, `encrypted` и `joined_members`. Если две комнаты имеют одинаковое имя, select автоматически добавляет alias/Room ID для различения.

Список room-specific entity обновляется при reload интеграции. Это намеренно: live sync обновляет состояние Matrix, но мы не создаём/удаляем HA entity из фонового callback без controlled reload.

## Routing profiles

В **Настройки → Устройства и службы → Matrix Extended → Настроить** можно задать объект `routing_profiles`, например:

```yaml
security:
  - "!security-room:example.org"
  - "#family:example.org"
system:
  - "!system-room:example.org"
```

После этого автоматизация не обязана знать Room ID:

```yaml
action: matrix_extended.send
data:
  route: security
  message: "🚨 Тревога у ворот"
```

`target` и `route` вместе использовать нельзя. Комнаты внутри route дедуплицируются с сохранением порядка.

## Обновляемые уведомления (`notification_key`)

Для прогресса/статуса не нужно создавать новое сообщение каждый раз:

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "download.movie.123"
  message: "⬇️ Фильм — 17%"
```

Следующий вызов:

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "download.movie.123"
  message: "⬇️ Фильм — 64%"
```

редактирует исходное сообщение через `m.replace`. Для каждой комнаты хранится свой original event ID. Mapping сохраняется в Home Assistant storage, поэтому обновления продолжают работать после restart/reload.

`notification_key` относится только к основному текстовому событию. Media не переотправляется автоматически и остаётся явным — это защищает от случайной повторной загрузки больших E2EE-вложений при каждом обновлении прогресса.

## Reaction actions

```yaml
action: matrix_extended.send
data:
  message: "Кто-то у ворот"
  media:
    - entity_id: camera.gate
  actions:
    - reaction: "💡"
      service: light.turn_on
      target:
        entity_id: light.gate
    - reaction: "🔕"
      service: input_boolean.turn_off
      target:
        entity_id: input_boolean.gate_alarm
```

Интеграция сохраняет эти действия только для event ID отправленного сообщения. Если разрешённый Matrix-пользователь поставит соответствующую реакцию в разрешённой комнате, action выполнится **один раз**. Реакция на любое другое сообщение ничего не вызовет.

Registry действий runtime-only: после перезапуска HA реакции на старые интерактивные сообщения не выполняются.

## Входящий текст

```yaml
trigger:
  - platform: event
    event_type: matrix_extended_message
condition:
  - condition: template
    value_template: "{{ trigger.event.data.message == 'статус' }}"
action:
  - action: matrix_extended.reply
    data:
      room: "{{ trigger.event.data.room_id }}"
      event_id: "{{ trigger.event.data.event_id }}"
      message: "Home Assistant онлайн ✅"
```

Payload содержит: `account_id`, `room_id`, `sender`, `event_id`, `timestamp`, `encrypted`, `verified`, `reply_to`, `thread_id`, `message`, `formatted_body`.

## Входящий reply

```yaml
trigger:
  - platform: event
    event_type: matrix_extended_reply
action:
  - action: logbook.log
    data:
      name: Matrix
      message: >-
        {{ trigger.event.data.sender }} ответил на
        {{ trigger.event.data.reply_to }}: {{ trigger.event.data.message }}
```

## Входящая реакция

```yaml
trigger:
  - platform: event
    event_type: matrix_extended_reaction
action:
  - action: logbook.log
    data:
      name: Matrix reaction
      message: >-
        {{ trigger.event.data.reaction }} на {{ trigger.event.data.reacts_to }};
        action={{ trigger.event.data.action_executed }}
```

## Входящее media

```yaml
trigger:
  - platform: event
    event_type: matrix_extended_media
action:
  - action: logbook.log
    data:
      name: Matrix media
      message: >-
        {{ trigger.event.data.media_type }}:
        {{ trigger.event.data.local_path }}
```

Payload также содержит `filename`, `content_type`, `mxc_uri`, `caption`, `local_path`, `download_error`.

## Reply / react / edit / redact из HA

```yaml
# Reply
action: matrix_extended.reply
data:
  room: "!room:example.org"
  event_id: "$event:example.org"
  message: "Готово ✅"
```

```yaml
# Reaction
action: matrix_extended.react
data:
  room: "!room:example.org"
  event_id: "$event:example.org"
  reaction: "👍"
```

```yaml
# Edit
action: matrix_extended.edit
data:
  room: "!room:example.org"
  event_id: "$event:example.org"
  message: "Загрузка — 47%"
```

```yaml
# Redact
action: matrix_extended.redact
data:
  room: "!room:example.org"
  event_id: "$event:example.org"
  reason: "Уведомление устарело"
```

## Threads

`send` и `reply` принимают `thread_id`.

```yaml
action: matrix_extended.send
data:
  message: "Новый кадр"
  thread_id: "$root_event:example.org"
  media:
    - entity_id: camera.front_door
```

## Тестирование

Перед merge/release обязательны два test-gate: быстрые regression-тесты и реальный стек Home Assistant + Synapse. После них отдельный package-gate собирает и побайтно проверяет установочный ZIP и публикует его вместе с SHA-256 checksum. Подробности — в `docs/TESTING.md`.

## Что сознательно не делается

- Matrix-текст не превращается автоматически в произвольный HA service call.
- Jinja/YAML из Matrix не исполняется.
- Cross-signing / Secure Backup не эмулируются поверх отсутствующего upstream API.
- Reaction action registry не хранится после перезапуска HA.
- Входящие файлы пока не имеют автоматической retention/очистки — каталог нужно учитывать в обслуживании диска.
