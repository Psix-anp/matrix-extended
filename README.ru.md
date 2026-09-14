<p align="center">
  <img src="custom_components/matrix_extended/brand/icon.png" width="96" alt="Matrix Extended">
</p>

<h1 align="center">Matrix Extended для Home Assistant</h1>

<p align="center">Безопасный двусторонний Matrix-канал для Home Assistant: E2EE, медиа, notify-сущности, входящие события, реакции, голос, геопозиция и устойчивая доставка.</p>

<p align="center"><a href="README.md">English</a> · <a href="README.ru.md"><strong>Русский</strong></a></p>

<p align="center">
  <img alt="Version" src="https://img.shields.io/badge/version-0.5.4-blue">
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5">
  <img alt="Matrix" src="https://img.shields.io/badge/Matrix-E2EE-0DBD8B">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

## Возможности

- Сквозное шифрование текста и медиа с постоянным crypto-state.
- Основная `notify`-сущность и отдельные `notify.*` сущности комнат.
- Графический редактор действий Home Assistant: выбор аккаунта, Media Browser, TTS/STT сущностей, языка, location entity, reaction actions и основных параметров сообщений.
- Home Assistant Media Browser: Local Media, Frigate и другие Media Source providers.
- Текст, notice, emote, Markdown/HTML, mentions, threads, replies, reactions, edits и redactions.
- Обновляемые уведомления через `notification_key`.
- Входящие message, reply, reaction, media, location, edit и redaction события.
- Диагностическая сущность **Последнее входящее событие** с отправителем, комнатой, event ID и типовыми атрибутами.
- Home Assistant TTS → Matrix voice, Matrix voice → Home Assistant STT, опциональный явный Assist.
- Persistent outbox на случай временной недоступности Matrix.
- Полная русская и английская локализация Home Assistant UI.

## Установка

### HACS

Добавьте этот репозиторий в HACS как пользовательский репозиторий типа **Integration**, установите **Matrix Extended**, перезапустите Home Assistant и откройте **Настройки → Устройства и службы → Добавить интеграцию → Matrix Extended**.

### Вручную

Скопируйте `custom_components/matrix_extended` в `/config/custom_components/matrix_extended`, перезапустите Home Assistant и добавьте интеграцию через **Настройки → Устройства и службы**.

Пароль Matrix используется только при первом входе. Дальше Matrix Extended использует полученный access token и сохранённое E2EE crypto-state.

## Графическая настройка

При первом подключении задаются homeserver, Matrix ID, пароль, комната по умолчанию и базовые параметры безопасности. После подключения откройте **Настройки → Устройства и службы → Matrix Extended → Настроить**.

Настройки разделены на понятные разделы:

- **Основные** — комната по умолчанию, проверка TLS и требование E2EE.
- **Входящие и безопасность** — включение входящих событий и allowlist Matrix-пользователей/комнат.
- **Входящие медиа** — скачивание, retention и ограничение занимаемого места.
- **Маршруты уведомлений** — графическое добавление, изменение и удаление именованных групп комнат без JSON.

Подробно: [Настройки](docs/SETTINGS.ru.md).

## Действия и автоматизации

Основной способ настройки — графический редактор действий Home Assistant. YAML по-прежнему полностью поддерживается и всегда доступен через **Редактировать в YAML**.

Основные действия: `matrix_extended.send`, `send_media`, `send_voice`, `transcribe_voice`, `send_location`, `reply`, `react`, `edit`, `redact` и `purge_media`.

Полное описание: [Действия и события](docs/ACTIONS.ru.md). Готовые YAML-примеры: [Примеры](docs/EXAMPLES.ru.md).

### Графический выбор медиа

`matrix_extended.send_media` открывает штатный Media Browser Home Assistant и не ограничивает provider-specific типы медиа. Если Frigate, Local Media или другой Media Source provider показывает клип/снимок/файл в Home Assistant, его можно выбрать графически.

Для камер, URL, локальных путей, нескольких вложений, thumbnail и расширенных метаданных используйте поле **Расширенное медиа** в `matrix_extended.send` или YAML.

## Входящие события и безопасность

Входящая обработка fail-closed: если она включена, **и отправитель, и комната** должны присутствовать в соответствующих allowlist. Собственные transaction echoes игнорируются.

Reaction actions привязываются только к конкретному исходящему Matrix event и могут иметь срок действия, лимит использований и список разрешённых пользователей. Полученный из Matrix текст, YAML или Jinja не выполняется как произвольное действие Home Assistant.

## Диагностика

Устройство интеграции показывает состояние соединения, шифрование комнаты по умолчанию, последнюю успешную отправку, последнюю ошибку и последнее входящее событие. Состояния локализованы; при отсутствии ошибок отображается **Ошибок нет**, а не `unknown`.

## Ограничения upstream

Релиз использует `matrix-nio==0.26.0`. Эта версия не предоставляет cross-signing API. `m.reaction` у matrix-nio 0.26.0 отправляется незашифрованным, поэтому реакцию и relation к целевому событию нельзя считать секретными данными даже в E2EE-комнате.

## Проверка релиза

Перед слиянием релиз проходит fast regression gate, чистую установку manifest-зависимостей на Python 3.14, реальный стек **Home Assistant 2026.9.2 + Synapse 1.160.0 + Element Web 1.12.26**, E2EE send/receive, notify entities, Media Browser send, outage/reconnect/outbox, restart Home Assistant, проверку фоновых задач и сборку проверенного install ZIP с SHA-256.

Подробнее: [Тестирование](docs/TESTING.ru.md).

## Лицензия

MIT — см. [LICENSE](LICENSE).
