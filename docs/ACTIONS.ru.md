# Действия и события Matrix Extended

Основной интерфейс — графический редактор действий Home Assistant. Те же действия полностью доступны в YAML.

## Исходящие действия

### `matrix_extended.send`

Основное универсальное действие Matrix Extended.

Используйте его для текста, Markdown/HTML, mentions, threads, обновляемых уведомлений, нескольких/расширенных медиа-вложений и безопасных reaction actions.

Основные поля:

- **Аккаунт** — config entry Matrix Extended; в YAML можно не указывать, если загружен ровно один аккаунт.
- **Комнаты** — один или несколько Matrix Room ID/alias.
- **Маршрут** — именованный route из настроек интеграции; одновременно с Комнаты не используется.
- **Ключ уведомления** — постоянный ключ; следующие отправки с тем же ключом редактируют исходный Matrix event.
- **Тип сообщения** — `text`, `notice` или `emote`.
- **Формат** — `text`, `html` или `markdown`.
- **Упомянуть пользователей / комнату** — нативные Matrix mentions.
- **ID ветки** — event ID корня thread.
- **Расширенное медиа** — структурированные вложения из HA entities, локальных путей, URL или Media Source ID.
- **Действия по реакциям** — заранее заданные Home Assistant actions, привязанные к реакциям на конкретное исходящее событие.

`matrix_extended.send` умеет возвращать response data и публикует жизненный цикл доставки через `matrix_extended_delivery`.

### `matrix_extended.send_media`

Открывает штатный Home Assistant Media Browser и отправляет выбранный Media Source item в Matrix. Selector принимает все типы Media Source, поэтому provider-specific элементы, например клипы/снимки Frigate, не отфильтровываются.

Для камер, URL, локальных путей, нескольких вложений, thumbnail, native voice metadata и явных размеров/duration используйте `matrix_extended.send` → **Расширенное медиа**.

### `matrix_extended.send_voice`

Синтезирует текст через Home Assistant TTS и отправляет результат как нативное Matrix voice message.

В графическом редакторе можно выбрать `tts.*` сущность и язык. `tts_options` остаётся расширенным object-полем, потому что разные TTS-интеграции используют разные параметры.

### `matrix_extended.transcribe_voice`

Распознаёт уже скачанное входящее Matrix voice через Home Assistant STT.

Matrix Extended сам создаёт отдельный каталог входящих медиа для каждого Matrix-аккаунта:

`/config/matrix_extended/incoming/<config_entry_id>/`

Точное расположение строится через `hass.config.path("matrix_extended", "incoming", entry.entry_id)`, поэтому при нестандартном каталоге конфигурации Home Assistant корневая часть может отличаться от `/config`.

При получении медиа интеграция сохраняет файл в этот каталог и публикует его полный путь в `trigger.event.data.local_path` события `matrix_extended_media`. В обычной автоматизации путь вручную составлять не нужно — передавайте `local_path` прямо в `matrix_extended.transcribe_voice`.

Из соображений безопасности действие принимает только обычные файлы внутри каталога входящих медиа выбранного Matrix-аккаунта; выход через `..`, symlink или путь другого аккаунта отклоняется.

Если STT-провайдеру нужен WAV/PCM, Matrix Extended может нормализовать поддерживаемый вход через штатный Home Assistant FFmpeg.

`assist: true` включается только явно. Голосовое сообщение не отправляется в Home Assistant Assist по умолчанию.

Готовый пример автоматизации: [EXAMPLES.ru.md — «Входящее голосовое Matrix → STT»](EXAMPLES.ru.md#4-входящее-голосовое-matrix--stt).

### `matrix_extended.send_location`

Отправляет Matrix location по явным latitude/longitude либо из Home Assistant entity с атрибутами `latitude` и `longitude`.

### `matrix_extended.reply`

Ответ на существующий Matrix event ID. Поддерживает тип сообщения, формат, mentions и threads.

### `matrix_extended.react`

Добавляет Matrix reaction к существующему событию.

В matrix-nio 0.26.0 событие `m.reaction` само по себе не шифруется. Не передавайте секретные данные в реакциях.

### `matrix_extended.edit`

Редактирует текстовое Matrix-событие через `m.replace`.

### `matrix_extended.redact`

Выполняет Matrix redaction существующего события.

### `matrix_extended.purge_media`

Удаляет скачанные входящие медиа выбранного Matrix Extended аккаунта и может вернуть количество удалённых файлов/байт.

## Reaction actions

Reaction action существует только если Home Assistant при отправке сообщения явно привязал его к конкретному исходящему событию. В определении можно задать:

- ключ реакции;
- конкретное Home Assistant action/service;
- target и data;
- срок действия в секундах;
- максимальное число использований;
- разрешённых Matrix-пользователей.

Полученный из Matrix текст, YAML или Jinja никогда не интерпретируется как произвольное действие Home Assistant.

## Notify-сущности

Каждый аккаунт создаёт `notify`-сущность комнаты по умолчанию и отдельные room-specific `notify` entities для joined rooms. Для обычных графических уведомлений можно использовать стандартное действие Home Assistant `notify.send_message` с нужной notify entity.

Matrix Extended-specific actions нужны, когда требуются routes, response data, advanced media, reactions, threads, voice и другие Matrix-specific возможности.

## Входящие события

Если входящая обработка включена и одновременно совпадают sender/room allowlist, Matrix Extended публикует:

| Event | Назначение |
| --- | --- |
| `matrix_extended_message` | Входящее текстовое сообщение |
| `matrix_extended_reply` | Входящий reply |
| `matrix_extended_reaction` | Входящая реакция и metadata reaction action |
| `matrix_extended_media` | Входящее image/video/audio/file; voice отмечается отдельно |
| `matrix_extended_location` | Входящая Matrix-геопозиция |
| `matrix_extended_edit` | Входящее редактирование |
| `matrix_extended_redaction` | Входящий redaction |
| `matrix_extended_delivery` | Жизненный цикл отправки: `sent`, `queued`, `failed`, `dropped` |

Общие metadata включают контекст аккаунта/config entry, комнату, отправителя, event ID, timestamp и состояние шифрования. События конкретных типов добавляют relation, media, voice, location или edit/redaction поля.

## Диагностика «Последнее входящее событие»

Сенсор **Последнее входящее событие** показывает тип события как state и metadata события как attributes, включая sender, room и event ID, когда они доступны. State локализуется в интерфейсе Home Assistant.

## Offline delivery

Если Matrix homeserver временно недоступен, поддерживаемые исходящие отправки сохраняются в persistent outbox. Интеграция отмечает потерю соединения, ставит сообщение в очередь и доставляет его после reconnect, не блокируя event loop Home Assistant.

Готовые примеры: [EXAMPLES.ru.md](EXAMPLES.ru.md). Настройки интеграции: [SETTINGS.ru.md](SETTINGS.ru.md).