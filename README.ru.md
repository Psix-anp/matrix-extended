<p align="center">
  <img src="custom_components/matrix_extended/brand/icon.png" width="96" alt="Matrix Extended">
</p>

<h1 align="center">Matrix Extended для Home Assistant</h1>

<p align="center">
  Компактная Matrix-интеграция для Home Assistant с E2EE, rich media, двусторонними событиями, устойчивой доставкой, голосом и геопозицией.
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.ru.md"><strong>Русский</strong></a>
</p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.0-blue">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5">
  <img alt="Matrix" src="https://img.shields.io/badge/Matrix-E2EE-0DBD8B">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

> **0.5.0** перед упаковкой релиза проверяется на реальном стеке **Home Assistant 2026.9.2 + Synapse 1.160.0 + Element Web 1.12.26**.

## Зачем Matrix Extended

Matrix Extended превращает Matrix в безопасный канал уведомлений и взаимодействия с Home Assistant, но не делает из текста чата неограниченную удалённую консоль.

- Сквозное шифрование текста и медиа.
- Вложения из `camera.*`, `image.*`, локального пути, URL и `media-source://`.
- Обычный текст, `notice`, `emote`, HTML и безопасный Markdown.
- Нативные Matrix mentions, replies, reactions, edits, redactions и threads.
- Отдельные notify-сущности комнат, discovery комнат, select комнаты по умолчанию и именованные маршруты.
- Обновляемые уведомления через `notification_key` вместо спама новыми сообщениями.
- Постоянная очередь доставки при временной недоступности homeserver.
- Явные reaction actions с TTL, лимитом использований и allowlist пользователей.
- Входящие сообщения, replies, reactions, media, edits, redactions и location как события Home Assistant.
- Нативная Matrix-геопозиция из координат или HA-сущности.
- Нативные Matrix voice messages, Home Assistant TTS → voice, voice → STT и явный voice → Assist.
- Retention входящих медиа, ограничение объёма и ручная очистка.
- Русская и английская локализация интерфейса Home Assistant.

## Скриншоты

Скриншоты снимаются настоящим Element Web в том же disposable E2E-стеке, который используется при проверке релиза.

<p align="center">
  <img src="docs/screenshots/element-rich-e2e.png" alt="Зашифрованные location и voice Matrix Extended в Element" width="820">
</p>

## Установка

### HACS

Когда репозиторий будет публичным, добавьте его в HACS как пользовательский репозиторий категории **Integration** и установите **Matrix Extended**.

### Вручную

Скопируйте:

```text
custom_components/matrix_extended
```

в:

```text
/config/custom_components/matrix_extended
```

Перезапустите Home Assistant и добавьте **Matrix Extended** через **Настройки → Устройства и службы**.

Пароль используется только для первоначального Matrix login. Дальше используются полученный access token и постоянное E2EE crypto-хранилище.

## Первичная настройка

Рекомендуемая схема:

1. Создать отдельный Matrix bot-account.
2. Пригласить его в зашифрованную комнату.
3. Оставить **Require E2EE** включённым.
4. Включать входящие события только если они действительно нужны.
5. Настроить одновременно **Allowed users** и **Allowed rooms** — входящие события проходят только при совпадении обоих allowlist.
6. Включить скачивание входящих медиа только если автоматизациям нужны локальные файлы.
7. Настроить срок хранения и максимальный размер каталога входящих медиа.

Постоянное crypto-состояние хранится в:

```text
/config/.storage/matrix_extended/<config_entry_id>/
```

Скачанные входящие файлы:

```text
/config/matrix_extended/incoming/<config_entry_id>/
```

## Быстрые примеры

### Отправить сообщение

```yaml
action: matrix_extended.send
data:
  target:
    - "#security:example.org"
  message: "Движение у ворот"
```

### Markdown + mention

```yaml
action: matrix_extended.send
data:
  route: security
  format: markdown
  message: "**Тревога:** дверь гаража открыта"
  mention_users:
    - "@seriy:example.org"
```

### Камера + безопасное действие по реакции

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Кто-то у ворот"
  media:
    - entity_id: camera.gate
      caption: "Свежий кадр"
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

Реакция может вызвать только конкретную службу Home Assistant, заранее привязанную HA к конкретному исходящему Matrix event. Текст Matrix, YAML и Jinja никогда не интерпретируются как произвольный service call.

### Обновлять одно сообщение вместо спама

```yaml
action: matrix_extended.send
data:
  route: system
  notification_key: "download.movie.123"
  message: "Загрузка — 64%"
```

Следующие вызовы с тем же ключом редактируют исходный Matrix event через `m.replace`.

### Отправить геопозицию

Явные координаты:

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  latitude: 52.3676
  longitude: 4.9041
  description: "Текущее положение"
```

Или HA-сущность с атрибутами `latitude` / `longitude`:

```yaml
action: matrix_extended.send_location
data:
  target:
    - "#family:example.org"
  entity_id: person.seriy
```

### Отправить готовое голосовое

```yaml
action: matrix_extended.send
data:
  target:
    - "#family:example.org"
  media:
    - path: /config/media/voice.ogg
      type: audio
      voice: true
```

### Home Assistant TTS → Matrix voice

```yaml
action: matrix_extended.send_voice
data:
  target:
    - "#security:example.org"
  text: "Внимание. Дверь гаража всё ещё открыта."
  language: ru-RU
```

`tts_engine` и специфические для провайдера `tts_options` необязательны.

### Matrix voice → Home Assistant STT

Используйте `local_path` из входящего события `matrix_extended_media`:

```yaml
action: matrix_extended.transcribe_voice
response_variable: voice_result
data:
  path: "{{ trigger.event.data.local_path }}"
  stt_entity: stt.whisper
  language: ru
```

Если STT-провайдер не принимает исходный OGG/Opus, Matrix Extended использует штатный Home Assistant FFmpeg и нормализует звук в поддерживаемый WAV/PCM.

### Распознанный голос → Assist

Выполнение Assist специально **выключено по умолчанию**. Оно включается только явно:

```yaml
action: matrix_extended.transcribe_voice
response_variable: voice_result
data:
  path: "{{ trigger.event.data.local_path }}"
  stt_entity: stt.whisper
  assist: true
```

Для любой автоматизации, которая может дойти до Assist, обязательно ограничивайте входящих Matrix-пользователей и комнаты allowlist’ами.

## Службы

| Служба | Назначение |
| --- | --- |
| `matrix_extended.send` | Текст, Markdown/HTML, mentions, media, threads, routes и reaction actions |
| `matrix_extended.send_voice` | Home Assistant TTS → native Matrix voice |
| `matrix_extended.transcribe_voice` | Скачанное Matrix voice → Home Assistant STT; опционально явный Assist |
| `matrix_extended.send_location` | Matrix `m.location` из координат или HA entity |
| `matrix_extended.reply` | Ответ на Matrix event |
| `matrix_extended.react` | Emoji reaction |
| `matrix_extended.edit` | Редактирование через `m.replace` |
| `matrix_extended.redact` | Redact Matrix event |
| `matrix_extended.purge_media` | Очистка скачанных входящих медиа с количеством файлов/байт в response |

Поля и selectors отображаются прямо в редакторе действий Home Assistant через `services.yaml`.

## Входящие события

| Event | Что означает |
| --- | --- |
| `matrix_extended_message` | Входящее текстовое сообщение |
| `matrix_extended_reply` | Входящий reply |
| `matrix_extended_reaction` | Входящая реакция и результат reaction action |
| `matrix_extended_media` | Входящее image/video/audio/file; voice помечается отдельно |
| `matrix_extended_location` | Входящая Matrix-геопозиция |
| `matrix_extended_edit` | Входящее редактирование |
| `matrix_extended_redaction` | Входящий redact |
| `matrix_extended_delivery` | Жизненный цикл исходящей доставки: `sent`, `queued`, `failed`, `dropped` |

Общие данные включают аккаунт, комнату, отправителя, event ID, timestamp, состояние шифрования и relation-поля. Rich payload дополнительно содержит имя/alias комнаты, display name отправителя, mentions и метаданные media, если они доступны.

## Delivery response и offline queue

`matrix_extended.send` умеет возвращать response с постоянным `delivery_id`, статусом доставки и списком Matrix events. Если Synapse временно недоступен, поддерживаемая отправка сохраняется в persistent outbox и доставляется после восстановления соединения вместо блокировки Home Assistant.

Тот же жизненный цикл публикуется отдельным событием `matrix_extended_delivery`, поэтому его можно использовать независимо от service response.

## Комнаты и маршруты

После Matrix sync интеграция создаёт:

- общую `notify` entity для текущей default room;
- отдельную `notify` entity для каждой joined room;
- select **Default room**;
- диагностические сущности соединения, пользователя, устройства, комнаты, последней отправки/приёма и ошибки.

Именованные маршруты избавляют автоматизации от жёстко прописанных Room ID:

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Сработала тревога"
```

## Модель безопасности

Matrix Extended намеренно оставляет возможности автоматизаций явными и ограниченными:

- `Require E2EE` запрещает отправку в plaintext-комнаты, когда включён.
- Входящая обработка ограничивается одновременно allowlist пользователя и комнаты.
- Matrix-текст никогда не становится исполняемым YAML, Jinja или произвольной службой HA.
- Reaction action существует только если Home Assistant сам привязал его к конкретному исходящему event.
- Reaction actions могут иметь TTL, `allowed_users` и `max_uses`.
- Voice transcription может читать только файлы каталога входящих медиа выбранного Matrix-аккаунта.
- Voice → Assist требует явного `assist: true`.
- Media retention/purge работает только внутри каталогов, которыми владеет интеграция.

### Ограничения upstream Matrix

В релизе намеренно остаётся `matrix-nio==0.26.0`. Эта версия не предоставляет cross-signing API. Кроме того, `m.reaction` отправляется незашифрованным, поэтому emoji и связь с target event видны homeserver даже в E2EE-комнате. Не используйте реакции для PIN, паролей и других секретов.

## Тестирование и release gate

Каждый релиз-кандидат обязан пройти:

1. source validation, compile и regression-тесты;
2. disposable real-stack Home Assistant 2026.9.2 + Synapse 1.160.0 + Element Web 1.12.26;
3. реальную E2EE-расшифровку в Element и отображение location/voice;
4. Synapse outage → persistent queue → автоматическое восстановление;
5. restart Home Assistant и проверку сохранённого one-shot reaction action;
6. проверку чистых runtime logs/background tasks;
7. сборку install ZIP, побайтовое сравнение с деревом компонента и SHA-256 checksum.

Подробнее: [`docs/TESTING.md`](docs/TESTING.md).

## Обновление с 0.4.x

Существующие config entries, access tokens, crypto stores, routing profiles и notification mappings сохраняются. Новые настройки 0.5 имеют безопасные значения по умолчанию. Старый YAML с `matrix_extended.send` продолжает работать как обычная текстовая отправка, пока новые поля явно не используются.

## Лицензия

MIT — см. [`LICENSE`](LICENSE).
