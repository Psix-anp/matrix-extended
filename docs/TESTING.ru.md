# Тестирование Matrix Extended

[English](TESTING.md) · **Русский**

Matrix Extended использует обязательные релизные gate-проверки. Релиз не сливается и не упаковывается из непроверенного коммита.

## 1. Быстрый regression gate

Запускается на Python 3.13:

```bash
python -m pip install -r requirements-test.txt
python ci/scripts/validate-source.py
python -m compileall -q custom_components/matrix_extended
pytest -q
```

Покрываются config/setup flow, контракты selector-ов, E2EE-зависимости, rich content, разрешение медиа, mentions/Markdown, сохранение и лимиты reaction actions, ответы/события доставки, входящие события и retention, безопасность voice/STT, notify-сущности, persistent outbox, контракты Element E2E стенда и сборка релизного пакета.

Количество тестов намеренно не фиксируется в документации: источником истины является вывод CI.

## 2. Проверка чистого manifest runtime

Запускается в свежем окружении Python 3.14 и устанавливает только зависимости, объявленные в manifest интеграции. Затем создаётся `matrix-nio` клиент с включённым шифрованием.

Эта проверка защищает от ситуации, когда тестовое окружение случайно скрывает отсутствующие runtime/E2EE зависимости.

## 3. Реальный Home Assistant + Synapse + Element

Одноразовый тестовый стек зафиксирован на версиях:

- Home Assistant `2026.9.2`
- Synapse `1.160.0`
- Element Web `1.12.26`

Gate создаёт временных Matrix-пользователей и зашифрованную комнату, выполняет реальный вход получателя в Element до отправки Home Assistant зашифрованных данных, затем проверяет:

1. Home Assistant запускается и принимает metadata сервисов Matrix Extended своим настоящим parser-ом.
2. Config entry Matrix Extended загружается и переживает reload.
3. Реальный зашифрованный текст проходит через Synapse и расшифровывается в Element.
4. В Home Assistant регистрируются основная и комнатные Matrix notify-сущности.
5. Rich Matrix events корректно отображаются в Element.
6. Графическое действие `matrix_extended.send_media` реально выполняется через Home Assistant Media Source.
7. Synapse останавливается при продолжающем работать Home Assistant, и интеграция фиксирует потерю соединения.
8. Отправка во время недоступности Matrix сохраняется в outbox.
9. После запуска Synapse очередь доставляется, а входящий/исходящий трафик восстанавливается без reload Home Assistant.
10. После перезапуска Home Assistant восстанавливаются config entry и сохранённое состояние интеграции.
11. Реальная Matrix-реакция обновляет диагностическую сущность **Последнее входящее событие**.
12. В runtime-логах нет предупреждений Matrix Extended о блокировке event loop и исключений от утёкших фоновых задач.
13. Реальные скриншоты Element загружаются как CI artifacts.

Showcase Element использует нейтральные тестовые координаты и публичный стиль карты. Провайдер карты нужен только CI; сама Matrix Extended отправляет стандартные Matrix location events.

## 4. Проверенный install ZIP

Запускается только после успешного завершения предыдущих gate-проверок:

```bash
python ci/scripts/build-release.py
```

Builder читает версию из `custom_components/matrix_extended/manifest.json`, создаёт `dist/matrix_extended-ha-install-v<version>.zip`, повторно открывает архив и побайтно сравнивает каждый файл архива с деревом компонента. CI также создаёт SHA-256 checksum.

Секреты, пароли, access token, Synapse registration secrets, crypto stores и runtime-конфигурация Home Assistant в пакет никогда не включаются.

## Локальный smoke test реального стека

На машине с Docker:

```bash
ci/scripts/prepare-synapse.sh
E2E_UID="$(id -u)" E2E_GID="$(id -g)" docker compose -f compose.test.yml up -d synapse
python ci/scripts/wait-http.py http://127.0.0.1:8008/_matrix/client/versions 90
MATRIX_REGISTRATION_SHARED_SECRET="$(cat .ci/synapse-shared-secret)" python ci/scripts/bootstrap-matrix.py
ci/scripts/prepare-ha.sh
docker compose -f compose.test.yml up -d --no-deps element
docker compose -f compose.test.yml up -d homeassistant
python ci/scripts/wait-http.py http://127.0.0.1:8123/api/onboarding 180
python ci/scripts/ha-e2e.py setup-send-reload
python ci/scripts/verify-ha-entities.py
python ci/scripts/verify-runtime.py send-media
```

Дополнительно CI запускает browser E2E, outage/outbox/recovery, restart Home Assistant, проверку входящей диагностики и gate установки пакета.

## Правило релиза

Не сливайте, не тегируйте и не публикуйте релизный пакет, пока fast regression, clean manifest runtime, real-stack и verified-package jobs не зелёные на точном release commit.
