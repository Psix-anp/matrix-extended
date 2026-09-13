# Private testing — Matrix Extended 0.5.0

This repository can stay private while 0.5.0 is tested in a real Home Assistant installation.

## Recommended test install

Use the verified install ZIP produced by GitHub Actions on `main`.

1. Open the latest successful **Matrix Extended tests** workflow on `main`.
2. Download the **verified install archive** artifact.
3. Extract `custom_components/matrix_extended` into `/config/custom_components/matrix_extended`.
4. Restart Home Assistant.
5. Add **Matrix Extended** from **Settings → Devices & services**.

For a manual source install, copy the `custom_components/matrix_extended` directory from `main` to the same Home Assistant path.

## Upgrade from 0.4.x

Back up `/config/.storage` before testing a development release. Existing Matrix Extended config entries, access tokens, E2EE crypto stores, routing profiles and notification mappings are expected to remain compatible with 0.5.0.

## First test checklist

- Integration loads without a repair or dependency error.
- Connection diagnostic becomes connected.
- Send a normal encrypted text message.
- Send Markdown + a native mention.
- Send a camera/image attachment.
- Call `matrix_extended.send_location` and confirm Element shows the position.
- Call `matrix_extended.send_voice` if a TTS provider is configured.
- Send a native Matrix voice message to the bot and test `matrix_extended.transcribe_voice` with an `stt.*` entity.
- Test one reaction action with `max_uses: 1`.
- Stop/restart Synapse once and confirm a send made while offline is queued and later delivered.
- Restart Home Assistant and confirm the integration reconnects automatically.

## Location maps in self-hosted Element

Matrix Extended sends the standard Matrix `m.location` event. No map provider is required for sending coordinates.

To **render a map** in a self-hosted Element Web, configure a Matrix-compatible map/tile style in Element or advertise one via your homeserver's `/.well-known/matrix/client`. The CI showcase uses OpenFreeMap only for the disposable test client; it is not a runtime dependency of Matrix Extended.

## What to report during private testing

Useful diagnostics:

- Home Assistant version.
- Matrix Extended version.
- Synapse/Dendrite/Conduit homeserver and version.
- Element/client version.
- The Matrix Extended diagnostic entities state.
- Relevant `custom_components.matrix_extended` log lines with access tokens/passwords removed.
- Whether the room is encrypted.

Do not post access tokens, passwords, crypto-store files, registration secrets or Authorization headers.

---

# Приватное тестирование — Matrix Extended 0.5.0

Репозиторий можно оставить закрытым до завершения проверки 0.5.0.

## Как поставить тестовую версию

Предпочтительный вариант — verified install ZIP из успешного GitHub Actions на ветке `main`.

1. Откройте последний успешный workflow **Matrix Extended tests** для `main`.
2. Скачайте artifact с проверенным install ZIP.
3. Распакуйте `custom_components/matrix_extended` в `/config/custom_components/matrix_extended`.
4. Перезапустите Home Assistant.
5. Добавьте **Matrix Extended** через **Настройки → Устройства и службы**.

Либо вручную скопируйте каталог `custom_components/matrix_extended` из `main`.

## Что проверить в первую очередь

- Интеграция загружается без dependency/repair ошибок.
- Диагностическая сущность соединения становится `connected`.
- Обычное E2EE-сообщение.
- Markdown и native mention.
- Фото/камера.
- `matrix_extended.send_location` и отображение точки в Element.
- `matrix_extended.send_voice`, если настроен TTS.
- Входящее Matrix voice → `matrix_extended.transcribe_voice` через `stt.*`.
- Reaction action с `max_uses: 1`.
- Остановка Synapse → отправка сообщения → статус `queued` → запуск Synapse → автоматическая доставка.
- Перезапуск Home Assistant → автоматическое восстановление соединения.

## Карта геопозиции

Интеграция отправляет стандартный Matrix `m.location`; отдельный tile server для самой отправки не нужен. Но self-hosted Element требует настроенный map/tile style, чтобы нарисовать карту. В disposable CI для витринного скриншота используется OpenFreeMap; это не зависимость интеграции.

## Что присылать при ошибке

Версии HA/Matrix Extended/Synapse/Element, состояние диагностических сущностей и релевантные строки лога. Токены, пароли, crypto-store и Authorization headers публиковать нельзя.
