# Matrix Extended — подключение и настройки

[English](SETTINGS.md) · **Русский**

Matrix Extended настраивается из интерфейса Home Assistant. YAML для добавления и настройки самой интеграции не требуется.

## Что нужно до подключения

Понадобятся:

- рабочий Matrix homeserver, доступный из Home Assistant;
- Matrix-аккаунт для интеграции;
- Matrix-комната, в которую этот аккаунт уже вступил;
- Home Assistant 2026.9.0 или новее.

Если планируются входящие автоматизации, safe commands или автоматический Voice Assist, лучше использовать отдельный Matrix-аккаунт интеграции.

## Первое подключение

Откройте **Настройки → Устройства и службы → Добавить интеграцию → Matrix Extended**.

В первой форме доступны:

| Поле интерфейса | Внутренний ключ | По умолчанию | Назначение |
| --- | --- | --- | --- |
| Homeserver | `homeserver` | — | базовый URL Matrix Client API, например `https://matrix.example.org` |
| Matrix ID | `user_id` | — | полный Matrix ID, например `@homeassistant:example.org` |
| Пароль | `password` | — | используется только для первого Matrix login; сама интеграция пароль не сохраняет |
| Комната по умолчанию | `default_room` | — | Room ID (`!...`) или alias (`#...`), используемый без явного target/route |
| Проверять TLS | `verify_ssl` | `true` | проверять TLS-сертификат homeserver |
| Требовать E2EE | `require_e2ee` | `true` | запрещать исходящую отправку в незашифрованные комнаты |
| Входящие события | `incoming_enabled` | `true` | запускать обработку входящих Matrix events |
| Разрешённые пользователи | `allowed_users` | пусто в форме | allowlist отправителей; при пустом поле на первом setup автоматически используется текущий Matrix ID |
| Разрешённые комнаты | `allowed_rooms` | пусто в форме | allowlist комнат; при пустом поле на первом setup автоматически используется `default_room` |
| Скачивать входящие медиа | `download_incoming_media` | `true` | скачивать/расшифровывать разрешённые Matrix-медиа для автоматизаций |

### Что происходит после нажатия «Отправить»

1. Matrix Extended входит на homeserver с указанными Matrix ID и паролем.
2. Пароль обменивается на Matrix access token и device ID. Сам пароль интеграция не сохраняет.
3. Проверяется `default_room`: Room ID с `!` принимается напрямую, alias с `#` разрешается через homeserver.
4. Повторное подключение того же сочетания `homeserver + user_id` отклоняется как дубликат config entry.
5. Если `allowed_users` и `allowed_rooms` оставлены пустыми, они автоматически инициализируются текущим пользователем и комнатой по умолчанию.
6. Home Assistant сохраняет access token, device ID, параметры соединения/безопасности и сгенерированный локальный store key в config entry.
7. Matrix Extended создаёт постоянное E2EE-состояние и запускает runtime connection.

При неверном логине Home Assistant покажет ошибку авторизации, при недоступном homeserver — ошибку соединения, а неверный Room ID/alias будет отмечен на поле комнаты.

## Где менять настройки после подключения

Откройте **Настройки → Устройства и службы → Matrix Extended → Настроить**.

Options Flow содержит пять разделов:

1. **Основные**
2. **Входящие и безопасность**
3. **Входящие медиа**
4. **Voice Assist**
5. **Маршруты уведомлений**

## Основные

### Комната по умолчанию — `default_room`

Room ID (`!...`) или alias (`#...`), который используется, если действие не задаёт `target` или `route`. Новый alias проверяется/разрешается перед сохранением.

Matrix Extended также создаёт select-сущность **Комната по умолчанию** со списком joined rooms. Выбор через select сохраняет новое значение.

### Проверять TLS — `verify_ssl`

По умолчанию: `true`.

Для обычного HTTPS homeserver оставляйте включённым. Отключайте только для заведомо доверенного локального/тестового сервера, чей сертификат Home Assistant сознательно не должен проверять.

Изменение `default_room` или `verify_ssl` обновляет connection settings, используемые runtime.

### Требовать E2EE — `require_e2ee`

По умолчанию: `true`.

При включении Matrix Extended отказывается отправлять сообщения в незашифрованные целевые комнаты. Выключение этой опции разрешает plaintext-комнаты, но не отключает шифрование в уже зашифрованных комнатах.

## Входящие и безопасность

### Принимать входящие события — `incoming_enabled`

По умолчанию после первого setup: `true`.

Включает входящий Matrix receiver. Если опция включена, оба allowlist ниже должны быть непустыми.

### Разрешённые пользователи — `allowed_users`

Matrix user IDs, которым разрешено попадать в Home Assistant, например:

```text
@seriy:example.org
@family:example.org
```

### Разрешённые комнаты — `allowed_rooms`

Matrix Room IDs/разрешённые идентификаторы комнат, из которых принимаются входящие события, например:

```text
!abcdef:example.org
```

Обработка работает **fail-closed**: событие проходит только тогда, когда одновременно совпали и отправитель, и комната. Собственные transaction echoes игнорируются.

Эта account-level политика проверяется до обработки входящих сообщений, медиа, реакций, safe commands и автоматического Voice Assist.

## Входящие медиа

### Скачивать и расшифровывать — `download_incoming_media`

По умолчанию: `true`.

Разрешённые входящие image/video/audio/file скачиваются и при необходимости расшифровываются для локальных автоматизаций. Событие `matrix_extended_media` содержит полный путь в `local_path`, а ошибку скачивания — в `download_error`.

Файлы разделены по config entry:

```text
/config/matrix_extended/incoming/<config_entry_id>/
```

Точный корень строится через `hass.config.path(...)`, поэтому на нестандартной установке он может отличаться от `/config`.

### Хранить, дней — `incoming_media_retention_days`

Диапазон: `0`…`365` дней.

Очистка скачанных медиа по возрасту. Значение `0` отключает именно age-based удаление; ограничение по размеру каталога всё равно может применяться.

### Лимит хранилища, МиБ — `incoming_media_max_mb`

Диапазон: `16`…`4096` МиБ.

Ограничивает собственный incoming-media каталог Matrix Extended. Очистка не выходит за этот каталог. Для немедленной ручной очистки есть `matrix_extended.purge_media`, которое может вернуть количество удалённых файлов и байт.

## Voice Assist — `voice_assist`

Автоматический Voice Assist **выключен по умолчанию**. Он не заменяет ручное действие `matrix_extended.transcribe_voice`.

Автоматический pipeline запускается только если одновременно выполнены условия:

- account-level `allowed_users`/`allowed_rooms` уже пропустили отправителя и комнату;
- Voice Assist включён;
- пришло именно нативное Matrix voice message;
- файл успешно скачан и имеет `local_path`;
- дополнительные Voice Assist allowlist, если заданы, тоже пропускают событие.

### Включить Voice Assist — `voice_assist_enabled`

После включения подходящее Matrix voice автоматически проходит Home Assistant STT, а распознанный текст передаётся в Conversation/Assist.

### STT entity — `voice_assist_stt_entity`

Необязательная `stt.*` сущность. Если не задана, используется default STT Home Assistant.

### Язык — `voice_assist_language`

Необязательный язык STT/Assist. При пустом значении pipeline использует fallback выбранного provider/Home Assistant.

### Conversation agent — `voice_assist_conversation_agent`

Необязательная `conversation.*` сущность. Если не указана, используется default conversation agent Home Assistant.

### Режим ответа — `voice_assist_reply_mode`

Варианты:

- `text` — ответить на исходное voice текстом Assist;
- `voice` — синтезировать ответ через Home Assistant TTS и отправить нативное Matrix voice;
- `both` — отправить и текст, и voice.

По умолчанию: `text`.

Если TTS в режиме `voice`/`both` завершится ошибкой, Matrix Extended при необходимости отправит текстовый fallback и запишет безопасно сокращённую ошибку Voice Assist.

### TTS entity — `voice_assist_tts_entity`

Необязательная `tts.*` сущность для режимов `voice` и `both`. При пустом значении используется TTS resolution Home Assistant.

### Разрешённые пользователи Voice Assist — `voice_assist_allowed_users`

Дополнительное сужение списка отправителей. Пустой список не добавляет нового ограничения, но основной account-level `allowed_users` продолжает действовать.

### Разрешённые комнаты Voice Assist — `voice_assist_allowed_rooms`

Дополнительное сужение по комнатам. Пустой список не добавляет нового ограничения, но account-level `allowed_rooms` продолжает действовать.

Эти параметры могут только **сузить** доступ Voice Assist и никогда не расширяют основную inbound policy.

Автоматический Voice Assist публикует событие `matrix_extended_voice_assist` со статусом `succeeded`/`failed`, отправителем, комнатой, transcript/conversation ID при наличии и безопасно очищенной ошибкой.

## Маршруты уведомлений

Маршрут — удобное имя для одной или нескольких Matrix-комнат. Управление полностью графическое: **Добавить маршрут**, **Изменить маршрут**, **Удалить маршрут**.

Пример:

```text
security → !garage:example.org, !gate:example.org
```

После этого:

```yaml
action: matrix_extended.send
data:
  route: security
  message: "Тревога"
```

Имя маршрута не может быть пустым, а маршрут должен содержать хотя бы одну комнату. `route` и явный `target` одновременно не используются.

## Безопасные Matrix-команды

Safe commands управляются действиями `matrix_extended.register_command` и `matrix_extended.unregister_command`. Это не произвольное выполнение service из текста чата.

Matrix-сообщение только выбирает заранее сохранённую команду; Home Assistant service/target/data или camera entity фиксируются при регистрации. Сначала применяется основной account-level inbound allowlist, затем команда может дополнительно сузить `allowed_users` и `allowed_rooms`.

Оба handler mode и готовые примеры: [EXAMPLES.ru.md](EXAMPLES.ru.md#11-matrix_extendedregister_command--безопасные-команды).

## Постоянные данные

Access/device данные находятся в Home Assistant config entry, а E2EE/registry state — в Home Assistant storage. Crypto-state хранится ниже:

```text
/config/.storage/matrix_extended/<config_entry_id>/
```

Не редактируйте `.storage` при работающем Home Assistant и не публикуйте config-entry data, access token, crypto-store или Authorization headers в bug reports.

## Диагностика

Устройство Matrix Extended показывает, в частности:

- состояние соединения;
- Matrix user/device ID;
- комнату по умолчанию и состояние её шифрования;
- последнюю успешную отправку;
- последнее входящее событие с типовыми атрибутами;
- последнюю ошибку;
- command/delivery runtime state, когда оно применимо.

Описание всех действий и response data: [ACTIONS.ru.md](ACTIONS.ru.md). Готовые автоматизации: [EXAMPLES.ru.md](EXAMPLES.ru.md).
