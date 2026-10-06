# Авторизация API по поверхности

Разные Bearer-токены в этом приложении не взаимозаменяемы. Начните с
[матрицы потребителей](README.md), затем используйте только механизм выбранной
поверхности. Ни один пример ниже не выдаёт доступ внешнему поставщику.

## Публичная витрина

Для большинства `/api/v1/*` сервер определяет tenant/storefront из
доверенного контекста. Без подписи разрешённый API host может обслуживать
только канонический `mvn/main`, пока выключен переключатель
`STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS`. Для другого storefront
доверенный SSR или same-origin proxy подписывает запрос короткоживущим HMAC
конвертом; клиентский браузер не получает этот ключ и не выбирает tenant из
payload, `Origin` или `X-Forwarded-Host`. При обязательной подписи даже
канонические запросы без неё получают `401`. Точные поля, срок и порядок
подписи описаны в [контракте витрины](../storefront-context-contract.md#canonical-v2-message).
Четыре открытых GET перечислены в
[классификаторе маршрутов](../../core/storefront_public_routes.py).

OpenAPI не показывает эти HMAC-заголовки: проверка выполняется до разбора
запроса FastAPI в [storefront_request_gateway.py](../../core/storefront_request_gateway.py).
Поэтому пустое поле `security` у публичной операции не означает свободную
запись или право выбрать другой storefront.

## Manager

`POST /login/access-token` принимает form-encoded `username` и `password`,
возвращает `access_token` и устанавливает cookie `access_token`
([auth.py](../../routers/auth.py)). Manager UI работает через HttpOnly cookie;
защищённые маршруты также принимают `Authorization: Bearer <JWT>`.
Выданный здесь JWT действует семь дней, но доступ проверяется на каждом
запросе: сотрудник должен оставаться активным, версия учётных данных и
членство в tenant — действующими
([security.py](../../core/security.py)). `POST /login/logout` удаляет браузерную
cookie; уже скопированный в Bearer JWT этот logout не отзывает.

Роль и область действия имеют значение помимо наличия токена:
`owner`, `admin`, `manager` допускаются к базовым Manager-операциям;
отдельные операции требуют владельца или системный tenant. Централизованная
[политика по operation ID](../../routers/manager_permission_policy.py)
накладывает эти требования на соответствующие маршруты. Базовый tenant
выводится из активного членства, не из поля запроса. Необязательный
`X-MVN-Manager-Storefront: <slug>` выбирает разрешённый storefront внутри
этого tenant; это не переключатель tenant
([контракт селектора](../manager-storefront-selector-contract.md#trust-boundary)).

Чтение собственной области для уже авторизованного локального сотрудника:

```bash
# Подставьте токен, выданный отдельно в локальном окружении.
API_BASE_URL=http://localhost:8000
curl -fsS -H "Authorization: Bearer ${MANAGER_TOKEN}" "${API_BASE_URL}/api/manager/me"
curl -fsS -H "Authorization: Bearer ${MANAGER_TOKEN}" "${API_BASE_URL}/api/manager/storefronts"
```

Не запускайте пример без своего `MANAGER_TOKEN`. Ответ `/me` показывает роль,
разрешённую область и capabilities; список storefront не раскрывает другие
tenant. Ошибки `401` и `403` означают разные причины — см.
[соглашения](conventions.md#ошибки-и-повторы).

## Внутренний Telegram-бот

`/api/internal/bot/v1/*` использует отдельный `BOT_API_TOKEN` через Bearer.
Он конфигурируется только у сервисного клиента и сверяется
[bot_api_security.py](../../core/bot_api_security.py); далее операции
проверяют сотрудника и бизнес-права. Контракт переноса и владельцы данных —
[bot-service-boundary.md](../bot-service-boundary.md#ownership), типизированные
модели — [api_contracts/bot.py](../../api_contracts/bot.py). Не используйте
Manager JWT или OAuth grant коннектора вместо сервисного токена.

## OAuth и MCP

Личный коннектор имеет собственные непрозрачные access/refresh-токены, которые
не проходят через Manager JWT. Первый выпуск использует фиксированный
`kitlane-chatgpt`, authorization code с PKCE S256 и точный resource
`https://api.mvn.by/api/connector/mcp`; динамическая регистрация клиентов
не поддерживается ([настройка](../chatgpt-connector.md#адрес-и-доступ)).
Требуется `kitlane:read`; записи обращений и поручений отдельно требуют
`kitlane:incoming:write` и `kitlane:tasks:write`. Access-токен живёт не дольше
15 минут, refresh — не дольше 30 дней или срока grant; refresh ротируется,
повторное использование уже потраченного refresh отзывает подключение
([connector_auth_service.py](../../services/connector_auth_service.py)).

Транспорт MCP и каждый tool call вновь проверяют действующий grant,
учётную запись, членство и нужный scope
([connector_mcp.py](../../services/connector_mcp.py)). Отзыв — в личном
профиле Manager; отключение плагина в клиенте не заменяет серверный отзыв.
Доступность callback и клиента проверяйте в реальной клиентской среде:
[handoff первого выпуска](../chatgpt-connector-handoff.md#статус-задач-и-следующий-шаг)
отделяет выпущенный backend от незавершённого пилота.
