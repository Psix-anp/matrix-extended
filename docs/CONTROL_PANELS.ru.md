# Нативные панели управления Matrix

[English](CONTROL_PANELS.md) · **Русский**

Native Matrix Control — поверхность управления `0.6.0b1` для Matrix Extended. Она превращает обычную Matrix-комнату в живое сообщение состояния/управления Home Assistant без передачи Matrix-клиенту токена Home Assistant.

## Объём `0.6.0b1`

- Панель использует **существующую Matrix-комнату**. Эта beta не создаёт комнаты или Spaces.
- Поддерживается **одна панель на комнату**.
- У панели один стабильный корневой `m.room.message`. Изменения состояний обновляют то же логическое сообщение через `m.replace`; новое root-сообщение при каждом изменении не создаётся.
- Управление выполняется Matrix-реакциями на root. Matrix передаёт только настроенную реакцию/ссылку на action; Home Assistant service, target и data остаются локально в Home Assistant.
- Будущий **Widget** Matrix Extended запланирован на следующую beta и в `0.6.0b1` не входит.

## Модель безопасности

Панели используют общий fail-closed policy Matrix Extended. Комната обязана входить в account `allowed_rooms`, а отправитель — в account `allowed_users`. Panel-level `allowed_users` может только дополнительно сузить account allowlist и никогда не может дать доступ новому Matrix-пользователю.

Actions заранее определены. Пользователь Matrix не может через реакцию передать произвольный Home Assistant service, target, YAML/Jinja или service-data object. Полученная реакция выбирает только сохранённый локально safe action.

В matrix-nio 0.26.0 само событие `m.reaction` не зашифровано E2EE. Поэтому авторизация не строится на шифровании реакции: Matrix Extended проверяет аутентифицированного Matrix sender, room, root/generation панели и настроенный action. Matrix power levels — дополнительная защита комнаты, но не замена allowlist интеграции.

## Создание панели через GUI Home Assistant

Откройте **Настройки → Устройства и службы → Matrix Extended → Настроить → Нативные панели управления Matrix → Добавить панель**.

Настраиваются:

- **Panel ID** — стабильный локальный идентификатор, например `garage`.
- **Matrix room** — существующий разрешённый resolved room ID.
- **Panel title** — заголовок root-сообщения.
- **Displayed entities** — Home Assistant entities, фактическое состояние которых показывается в сообщении.
- **Users allowed to control this panel** — необязательное дополнительное ограничение; пустое поле означает всех account-authorized senders.
- **State update debounce** — объединение быстрых изменений состояний. По умолчанию 1,5 с, допустимо 0,25–10 с.

После создания draft добавьте actions. У каждого action есть стабильный ID, уникальная реакция, label, Home Assistant service, target, необязательный YAML service data и `confirmation_required`.

GUI использует штатные selectors Home Assistant для service и target. Расширенный service data вводится YAML-текстом и обязан разбираться в mapping.

## Обычные и опасные действия

Обычный action выполняется после одной разрешённой реакции на root панели.

Для рискованных операций — открыть замок, гараж/ворота, снять сигнализацию, выключить критичную automation — ставьте `confirmation_required: true`. Тогда Matrix Extended создаёт confirmation reply и ждёт до **30 секунд** реакцию `✅` или `❌`. Подтвердить может только **тот же отправитель**, который инициировал action. Confirmation привязан к panel/action generation, одноразовый и атомарный. Перезагрузка Home Assistant инвалидирует ожидающие подтверждения — они не выполняются после рестарта.

Видимое состояние панели определяется фактическим HA state после вызова service. Сам факт успешного service call не считается доказательством изменения устройства.

## Закрепление и Matrix permissions

Matrix Extended пытается добавить стабильный root в `m.room.pinned_events`, сохраняя чужие уже закреплённые события. Matrix-аккаунту нужен достаточный power level для изменения pinned events.

Ошибка pin не валит интеграцию: панель может продолжить работу, а diagnostics покажет `pin_status`/ошибку. Постоянного агрессивного re-pin loop нет; попытка выполняется при создании, startup recovery и явном Repair.

## Живые обновления, debounce и недоступность Matrix

Отслеживаются только entities, выбранные для панели. Обновления event-driven от HA state changes; polling отсутствует. Настроенный `debounce` объединяет частые изменения, а render hash не отправляет `m.replace`, если итоговый текст не изменился.

При временной **недоступности** Matrix изменения панели не складываются по одному в обычный persistent outbox. Manager сохраняет/объединяет только последнее желаемое состояние и после восстановления соединения отправляет актуальный render. Это предотвращает шквал устаревших edits.

## Удалённый или redacted root: `needs_repair`

Если известный root панели пропал или был redacted, runtime получает состояние `needs_repair`. Matrix Extended намеренно **не** создаёт root автоматически, чтобы ошибка комнаты/permissions не вызвала message storm.

Откройте **Настроить → Нативные панели управления Matrix → Восстановить сообщение панели**. Явное восстановление (Repair) создаёт ровно один новый root, переводит controls на новую generation и повторно пытается pin. Конфигурация самой панели при этом не меняется.

## Диагностика

Интеграция создаёт выключенный по умолчанию diagnostic sensor **Панели управления**. Его state — количество активных панелей. Attributes содержат ограниченные snapshots: panel ID, room ID, root event ID, runtime state, pin status, watched entities, action IDs, timestamps/errors обновления и число pending confirmations. Service data, access tokens и другие secrets туда не попадают.

## YAML import/export

GUI умеет экспортировать и импортировать одну валидированную панель как YAML. Import проверяется относительно текущих account room/user allowlists, а замена существующей панели требует отдельного подтверждения.

Пример:

```yaml
panel_id: garage
room_id: "!garage:example.org"
title: Гараж
enabled: true
entities:
  - entity_id: cover.garage
    label: Ворота гаража
  - entity_id: light.garage
    label: Свет гаража
actions:
  - id: light_toggle
    reaction: "💡"
    label: Переключить свет
    service: light.toggle
    target:
      entity_id: light.garage
    data: {}
    confirmation_required: false
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

`room_id` должен быть resolved ID вида `!room:server` и входить в account `allowed_rooms`. Reaction и action ID внутри панели должны быть уникальными.

Практические варианты для гаража, сигнализации и света/климата: [Примеры](EXAMPLES.ru.md).