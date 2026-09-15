# Действия и события Matrix Extended

[English](ACTIONS.md) · **Русский**

Основной интерфейс — графический редактор действий Home Assistant. YAML полностью поддерживается и нужен для сложных шаблонов, `response_variable` и некоторых расширенных объектов.

## Общие правила

Поля **Аккаунт**, **Комнаты** и **Маршрут** повторяются в нескольких действиях:

- `account` — config entry Matrix Extended. Если загружен ровно один аккаунт, в YAML его можно не указывать. При нескольких аккаунтах поле обязательно.
- `target` — список Matrix Room ID/alias, например `!room:example.org` или `#family:example.org`.
- `route` — именованный маршрут из настроек Matrix Extended. `target` и `route` одновременно не используются.
- если не заданы ни `target`, ни `route`, используется комната по умолчанию аккаунта.
- `thread_id` — event ID корня Matrix thread. Это не ID сообщения, на которое нужно ответить; для reply используется отдельное `event_id`.

Действия `send`, `send_voice` и `send_location` поддерживают response data. Типичный ответ содержит:

```yaml
delivery_id: "..."
status: sent
events:
  - room_id: "!room:example.org"
    event_id: "$event"
    kind: text
```

Для media-события в записи `events` также может быть `media_index`. Возможные статусы жизненного цикла: `sent`, `queued`, `failed`, `dropped`.

## `matrix_extended.send`

Универсальная отправка текста и/или расширенных медиа. Поддерживает E2EE, Markdown/HTML, mentions, threads, обновляемые уведомления и безопасные действия по реакциям.

### Поля

| Поле | Обяз. | По умолчанию | Что означает |
| --- | --- | --- | --- |
| `account` | нет | единственный аккаунт | Matrix Extended config entry |
| `target` | нет | default room | список комнат; нельзя вместе с `route` |
| `route` | нет | — | именованный маршрут; нельзя вместе с `target` |
| `notification_key` | нет | — | стабильный ключ обновляемого уведомления; повторная отправка с тем же ключом редактирует исходное событие |
| `message` | нет* | `""` | текст; можно пустой только если есть `media` |
| `msgtype` | нет | `text` | `text`, `notice`, `emote` |
| `format` | нет | `text` | `text`, `markdown`, `html` |
| `mention_users` | нет | `[]` | Matrix user IDs для `m.mentions` |
| `mention_room` | нет | `false` | room-wide mention |
| `thread_id` | нет | — | event ID корня thread |
| `media` | нет* | `[]` | одно или несколько расширенных вложений |
| `actions` | нет | `[]` | безопасные Home Assistant actions, запускаемые конкретными реакциями |

`message` или `media` должны присутствовать. `notification_key` и `actions` требуют текстовое `message`.

### `media`: поля одного вложения

В одном элементе должен быть **ровно один источник**:

- `entity_id` — Home Assistant entity, обычно `camera.*`;
- `path` — локальный путь, разрешённый Home Assistant;
- `url` — HTTP/HTTPS URL;
- `media_source` — Home Assistant Media Source ID.

Дополнительные поля:

- `type` — `auto`, `image`, `video`, `audio`, `file`; обычно оставляйте `auto`;
- `filename` — имя файла в Matrix;
- `caption` — подпись;
- `formatted_caption` — HTML-подпись; используется только вместе с `caption`;
- `width`, `height` — размеры медиа;
- `duration_ms` — длительность в миллисекундах;
- `voice` — пометить аудио как нативное Matrix voice message;
- `thumbnail` — YAML-only вложенный media object для превью; вложенные thumbnail не допускаются.

### `actions`: действие по реакции

Каждый объект содержит:

- `reaction` — ключ реакции, например `✅`;
- `service` — фиксированное действие HA в формате `domain.service`;
- `target`, `data` — сохранённые target/data этого действия;
- `expires_in` — 1…604800 секунд, по умолчанию 3600;
- `max_uses` — 1…100, по умолчанию 1;
- `allowed_users` — необязательное дополнительное ограничение по Matrix user ID.

Входящий текст Matrix не может подменить `service`, `target` или `data`.

Готовые варианты: [EXAMPLES.ru.md — send](EXAMPLES.ru.md#1-matrix_extendedsend--основная-отправка).

## `matrix_extended.send_media`

Упрощённое действие для **одного** элемента Home Assistant Media Browser. Подходит для Local Media, Frigate и других Media Source providers.

| Поле | Обяз. | По умолчанию | Что означает |
| --- | --- | --- | --- |
| `account` | нет | единственный аккаунт | Matrix Extended config entry |
| `target` | нет | default room | комнаты |
| `route` | нет | — | маршрут вместо `target` |
| `media_picker` | да | — | объект, возвращённый selector Media Browser |
| `caption` | нет | — | подпись |
| `voice` | нет | `false` | нативное Matrix voice для выбранного аудио |
| `thread_id` | нет | — | корень thread |

`send_media` внутри преобразует выбор Media Browser и вызывает основной `send`. Для камер, URL, нескольких файлов, thumbnail или ручных метаданных используйте `send` → `media`.

После исправления v0.5.6 защищённые внутренние HA Media Source URL подписываются штатным временным `authSig`; Frigate timestamp VOD преобразуется в MP4 recording proxy перед загрузкой.

Примеры: [EXAMPLES.ru.md — send_media](EXAMPLES.ru.md#2-matrix_extendedsend_media--media-browser).

## `matrix_extended.send_voice`

Преобразует текст через Home Assistant TTS и отправляет полученное аудио как нативное Matrix voice message.

| Поле | Обяз. | По умолчанию | Что означает |
| --- | --- | --- | --- |
| `account` | нет | единственный аккаунт | Matrix Extended config entry |
| `target` | нет | default room | комнаты |
| `route` | нет | — | маршрут |
| `text` | да | — | текст для озвучивания; пустая строка запрещена |
| `tts_engine` | нет | default TTS | `tts.*` сущность или совместимый provider ID |
| `language` | нет | provider/default | язык/locale; интеграция умеет сопоставить, например, `ru-RU` с `ru` |
| `tts_options` | нет | `{}` | provider-specific параметры, например голос |
| `thread_id` | нет | — | корень thread |

Возвращает `delivery_id`, `status`, `events`.

Примеры: [EXAMPLES.ru.md — send_voice](EXAMPLES.ru.md#3-matrix_extendedsend_voice--tts--matrix-voice).

## `matrix_extended.transcribe_voice`

Распознаёт скачанное входящее Matrix voice через Home Assistant STT. При несовместимом OGG/Opus интеграция может нормализовать вход в WAV/PCM через штатный Home Assistant FFmpeg.

Каталог каждого аккаунта:

`/config/matrix_extended/incoming/<config_entry_id>/`

Точное расположение строится через `hass.config.path(...)`; при нестандартном config root префикс может отличаться. Нормальный источник `path` в автоматизации — `trigger.event.data.local_path` события `matrix_extended_media`.

Для безопасности разрешены только обычные файлы внутри incoming-каталога выбранного аккаунта. `..`, symlink и файл другого аккаунта отклоняются.

| Поле | Обяз. | По умолчанию | Что означает |
| --- | --- | --- | --- |
| `account` | нет | единственный аккаунт | аккаунт, которому принадлежит файл |
| `path` | да | — | полный `local_path` или имя относительно incoming-каталога |
| `stt_entity` | нет | default STT | `stt.*` entity |
| `language` | нет | язык HA | язык распознавания |
| `audio_format` | нет | `ogg` | `ogg` или `wav` |
| `codec` | нет | `opus` | `opus` или `pcm` |
| `bit_rate` | нет | `16` | глубина: `8`, `16`, `24`, `32` |
| `sample_rate` | нет | `48000` | `8000`, `11000`, `16000`, `18900`, `22000`, `32000`, `37800`, `44100`, `48000` |
| `channels` | нет | `1` | `1` или `2` |
| `assist` | нет | `false` | после STT передать текст в HA Conversation/Assist |
| `conversation_agent` | нет | default agent | `conversation.*` agent при `assist: true` |
| `conversation_id` | нет | новый диалог | существующий conversation ID |

Ответ:

- `text` — распознанный текст;
- `stt_entity` — фактически использованная STT entity;
- `language` — фактически выбранный язык;
- `normalized` — потребовался ли FFmpeg WAV/PCM fallback;
- `assist_executed` — запускался ли Assist;
- `assist` — результат Assist, только если он запускался.

Примеры: [EXAMPLES.ru.md — transcribe_voice](EXAMPLES.ru.md#4-matrix_extendedtranscribe_voice--matrix-voice--sttassist).

## `matrix_extended.send_location`

Отправляет стандартное Matrix `m.location`. Есть два взаимоисключающих режима: entity или явные координаты.

| Поле | Обяз. | Что означает |
| --- | --- | --- |
| `account` | нет | Matrix Extended config entry |
| `target` / `route` | нет | получатели |
| `entity_id` | условно | `person`, `device_tracker` или другая entity с `latitude` и `longitude` |
| `latitude` | условно | широта -90…90 |
| `longitude` | условно | долгота -180…180 |
| `description` | нет | подпись; для entity fallback — friendly name |
| `thread_id` | нет | корень thread |

Укажите либо `entity_id`, либо **оба** `latitude` + `longitude`. Смешивать два режима нельзя. Возвращает delivery response.

Примеры: [EXAMPLES.ru.md — send_location](EXAMPLES.ru.md#5-matrix_extendedsend_location--геопозиция).

## `matrix_extended.reply`

Ответ на существующее Matrix-событие.

| Поле | Обяз. | По умолчанию | Что означает |
| --- | --- | --- | --- |
| `account` | нет | единственный аккаунт | аккаунт |
| `room` | нет | default room | одна комната |
| `event_id` | да | — | event ID сообщения, на которое отвечаем |
| `message` | да | — | текст ответа |
| `msgtype` | нет | `text` | `text`, `notice`, `emote` |
| `format` | нет | `text` | `text`, `markdown`, `html` |
| `mention_users` | нет | `[]` | нативные mentions |
| `mention_room` | нет | `false` | room-wide mention |
| `thread_id` | нет | — | если reply должен одновременно находиться в thread |

Обычно `room` и `event_id` берутся прямо из входящего `matrix_extended_message`/`matrix_extended_reply`.

Примеры: [EXAMPLES.ru.md — reply](EXAMPLES.ru.md#6-matrix_extendedreply--ответ-на-входящее-сообщение).

## `matrix_extended.react`

Добавляет `m.reaction` к существующему Matrix-событию.

Поля: `account`, необязательный `room`, обязательные `event_id` и `reaction`.

В используемом `matrix-nio 0.26.0` событие `m.reaction` само по себе не шифруется. Не помещайте секреты в ключ реакции.

Примеры: [EXAMPLES.ru.md — react](EXAMPLES.ru.md#7-matrix_extendedreact--реакция).

## `matrix_extended.edit`

Редактирует текстовое Matrix-событие через `m.replace`.

Поля: `account`, необязательный `room`, обязательные `event_id` и `message`, а также `msgtype` (`text`/`notice`/`emote`) и `format` (`text`/`markdown`/`html`).

Для прогресса, который должен обновляться многократно, обычно проще `send` + `notification_key`. `edit` полезен, когда event ID уже известен.

Примеры: [EXAMPLES.ru.md — edit](EXAMPLES.ru.md#8-matrix_extendededit--редактирование).

## `matrix_extended.redact`

Matrix redaction существующего события. Это серверное Matrix redaction, а не локальное удаление записи Home Assistant.

Поля: `account`, необязательный `room`, обязательный `event_id`, необязательный `reason`.

Примеры: [EXAMPLES.ru.md — redact](EXAMPLES.ru.md#9-matrix_extendedredact--redaction).

## `matrix_extended.purge_media`

Удаляет скачанные входящие медиа выбранного Matrix Extended аккаунта из его incoming-каталога.

Единственное поле — `account`; его можно опустить только при одном загруженном аккаунте.

Response data:

```yaml
removed_files: 12
removed_bytes: 3456789
```

Примеры: [EXAMPLES.ru.md — purge_media](EXAMPLES.ru.md#10-matrix_extendedpurge_media--очистка-входящих-медиа).

## `matrix_extended.register_command`

Регистрирует или заменяет безопасную Matrix-команду. Входящее сообщение выбирает **только заранее сохранённую команду** и не может подменить Home Assistant action, target/data или camera entity.

Общие поля:

| Поле | Обяз. | По умолчанию | Что означает |
| --- | --- | --- | --- |
| `account` | нет | единственный аккаунт | Matrix Extended config entry |
| `id` | да | — | стабильный ID команды; повторная регистрация этого ID заменяет определение |
| `trigger` | да | — | нормализованная фраза без ведущего `!`, например `garage open` |
| `aliases` | нет | `[]` | дополнительные фразы |
| `description` | нет | `""` | описание |
| `allowed_users` | нет | `[]` | дополнительно сужает account allowlist |
| `allowed_rooms` | нет | `[]` | дополнительно сужает account allowlist |
| `progress` | нет | `true` | отправлять промежуточный ответ о выполнении |
| `handler_type` | да | — | `service` или `camera_snapshot` |

### Режим `handler_type: service`

- `service` — обязательно, например `light.turn_on`;
- `target` — фиксированный target;
- `data` — фиксированные service data;
- `entity_id` здесь запрещён.

### Режим `handler_type: camera_snapshot`

- `entity_id` — обязательно и должно быть `camera.*`;
- `caption` — подпись, по умолчанию `Camera snapshot`;
- `service`, `target`, `data` в этом режиме запрещены.

Response data содержит `id`, `trigger`, `handler_type`.

Примеры обоих режимов: [EXAMPLES.ru.md — register_command](EXAMPLES.ru.md#11-matrix_extendedregister_command--безопасные-команды).

## `matrix_extended.unregister_command`

Удаляет зарегистрированную команду по стабильному `id`.

Поля: необязательный `account`, обязательный `id`.

Ответ:

```yaml
id: garage_open
removed: true
```

`removed: false` означает, что такого ID в реестре уже не было.

Пример: [EXAMPLES.ru.md — unregister_command](EXAMPLES.ru.md#12-matrix_extendedunregister_command--удаление-команды).

## Notify-сущности

Каждый аккаунт создаёт `notify`-сущность комнаты по умолчанию и room-specific `notify` entities для joined rooms. Для обычного текста можно использовать стандартное действие Home Assistant `notify.send_message`. Matrix Extended actions нужны для routes, response data, rich media, reaction actions, threads, voice и других Matrix-специфичных возможностей.

## Входящие события

Если входящая обработка включена и одновременно проходят sender/room allowlist, Matrix Extended публикует:

| Event | Назначение |
| --- | --- |
| `matrix_extended_message` | входящее текстовое сообщение |
| `matrix_extended_reply` | входящий reply |
| `matrix_extended_reaction` | входящая реакция и metadata reaction action |
| `matrix_extended_media` | image/video/audio/file; voice отмечается отдельно |
| `matrix_extended_location` | геопозиция |
| `matrix_extended_edit` | редактирование |
| `matrix_extended_redaction` | redaction |
| `matrix_extended_delivery` | `sent`, `queued`, `failed`, `dropped` |

Общие metadata: `account_id`, `room_id`, sender, `event_id`, timestamp, состояние шифрования. События конкретных типов добавляют свои поля. Для входящего media особенно полезны `voice`, `content_type`, `local_path`, `download_error`.

## Offline delivery

Если homeserver временно недоступен, поддерживаемые отправки `send` сохраняются в persistent outbox. `matrix_extended_delivery` сначала получает `queued`, а после reconnect — `sent` либо `dropped` при постоянной ошибке.

Полные копируемые автоматизации: [EXAMPLES.ru.md](EXAMPLES.ru.md). Настройки интеграции: [SETTINGS.ru.md](SETTINGS.ru.md).
