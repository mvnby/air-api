# API Kitlane: с чего начать

Этот указатель разделяет контракты по потребителю. Наличие пути в Swagger UI
не означает, что его можно вызывать с любым токеном или использовать как
внешний партнёрский API. Для интеграции сначала выберите строку ниже, затем
проверьте конкретную операцию в схеме и профильном контракте.

| Потребитель | Поверхность | Доступ и основной контракт |
| --- | --- | --- |
| Публичная витрина `mvnby/mvn-web` | Прежде всего `/api/v1/*`: каталог, контент, обращения, заказ | Контекст витрины задаёт доверенный серверный запрос; условия подписи и четыре исключения описаны в [контракте витрины](../storefront-context-contract.md#protected-public-surfaces). Это не произвольный API для записи от имени tenant. |
| Manager UI и авторизованный сотрудник | `/api/manager/*`, вход через `/login/*` | JWT/cookie, живое членство в tenant, роль и права конкретной операции; см. [авторизацию](authentication.md#manager). |
| Сервис штатного Telegram-бота | `/api/internal/bot/v1/*` | Выделенный `BOT_API_TOKEN`, затем проверка сотрудника в бизнес-операциях; см. [границу бота](../bot-service-boundary.md#ownership). Это не пользовательский или партнёрский токен. |
| Личное подключение ChatGPT | `/api/connector/mcp` и `/api/connector/oauth/*` | Отдельный OAuth grant с точным MCP resource и scopes; см. [подключение](../chatgpt-connector.md#адрес-и-доступ), [аудит первого выпуска](../chatgpt-connector-handoff.md#что-выпущено-и-можно-подключать). |
| Сервис Белзакупки, прямой приём | `POST /api/integrations/tenders/leads` | Отдельный серверный Bearer key и фиксированная активная компания/витрина; выключен по умолчанию. Нативный формат, повторы и границы — в [контракте приёма](../belzakupki-intake.md#direct-push-intake-849-first-release-slice). |
| Внешний поставщик | Публичного supplier API сейчас нет | `/api/manager/suppliers` и связанные пути обслуживают внутреннюю платформу. Требования к возможной интеграции — [ниже](#граница-будущей-интеграции-поставщика). |

Проверенный код регистрации поверхностей —
[app_routing.py](../../core/app_routing.py), компоновщики
[api.py](../../routers/api.py) и [manager.py](../../routers/manager.py).
Пути `/api/health` и `/api/ready` служат проверкам приложения; они не дают
доступа к бизнес-данным.

## Навигация по доменам

Эта карта помогает найти код и профильный контракт, когда нужно изменить API.
Указанные пути — ориентиры для поиска в схеме, а не полный список методов;
доступ по-прежнему определяется таблицей потребителей выше и правами операции.

| Область | Путь для поиска | Владелец контракта и документация |
| --- | --- | --- |
| Публичный каталог и характеристики | `GET /api/v1/products`, `GET /api/v1/filters/config`, `/api/v1/specs/*` | [api_products.py](../../routers/api_products.py), [схемы товаров](../../schemas.py), [таксономия](../catalog/feature-taxonomy-guide.md), [код модели и номинальный класс](../catalog/public-product-identity.md) |
| Управление каталогом и характеристиками | `/api/manager/catalog-management/*`, `/api/manager/products/*`, `/api/manager/features/*` | [manager_catalog_management.py](../../routers/manager_catalog_management.py), [manager_features.py](../../routers/manager_features.py), [рабочая область](../catalog-management-workspace.md) |
| Контент и подборки | `/api/v1/content/*`, `/api/manager/product-collections/*` | [api_content.py](../../routers/api_content.py), [manager_product_collections.py](../../routers/manager_product_collections.py), [контракт подборок](../product-collections.md) |
| Медиа и галерея | `/api/manager/media/assets/*`, `/api/manager/gallery/*` | [manager_media_library.py](../../routers/manager_media_library.py), [manager_media_gallery.py](../../routers/manager_media_gallery.py), [публикация медиа](../catalog-media-publication.md) |
| Услуги и цены монтажа | `/api/v1/service-pricing/*`, `/api/manager/installation-rates/*`, `/api/manager/service-catalog/*` | [api_service_pricing.py](../../routers/api_service_pricing.py), [manager_installation_rates.py](../../routers/manager_installation_rates.py), [контракт сметы](../installation-estimate-contract.md) |
| Поставки и данные поставщиков | `/api/manager/suppliers/*`, `/api/manager/supplier-sources/*`, `/api/manager/supplier-offers/*` | [manager_supply.py](../../routers/manager_supply.py), [manager_supplier_mapping.py](../../routers/manager_supplier_mapping.py), [схемы привязок](../../schemas_supplier_mapping.py); это внутренние маршруты, см. [границу ниже](#граница-будущей-интеграции-поставщика) |
| Клиенты и реквизиты | `/api/manager/customers/*` | [manager_customers.py](../../routers/manager_customers.py), [рабочая область клиента](../customer-workspace.md) |
| Обращения и входящие | `/api/v1/leads/*`, `/api/manager/leads/*`, `/api/manager/incoming/*` | [api_leads.py](../../routers/api_leads.py), [manager_leads.py](../../routers/manager_leads.py), [manager_incoming.py](../../routers/manager_incoming.py), [сценарий входящих](../incoming-triage-workspace.md) |
| Заказы | `POST /api/v1/orders`, `/api/manager/orders/*` | [api_orders.py](../../routers/api_orders.py), [manager_orders.py](../../routers/manager_orders.py), [рабочая область заказа](../order-workspace-usability.md) |
| Документы заказа и шаблоны | `/api/manager/orders/{order_id}/documents`, `/api/manager/document-system/*` | [manager_docs.py](../../routers/manager_docs.py), [модуль документов](../../modules/documents/api/router.py), [архитектура](../document-module-architecture.md) |
| Поручения и календарь | `/api/manager/personal-tasks/*`, `GET /api/manager/calendar/events` | [manager_personal_tasks.py](../../routers/manager_personal_tasks.py), [manager_calendar.py](../../routers/manager_calendar.py), [контракт первого MCP-выпуска](../chatgpt-connector-handoff.md#что-выпущено-и-можно-подключать) |
| Личные записи звонков | `/api/manager/call-recordings/*` | [manager_call_recordings.py](../../routers/manager_call_recordings.py), [записи звонков](../call-recordings.md); отдельный readonly Drive OAuth, личный staff/tenant/storefront scope, выключенный по умолчанию pipeline и явное adoption |
| Настройки и доступ | `/api/manager/settings/*`, `/api/manager/storefront-settings/*`, `GET /api/manager/me` | [manager_settings.py](../../routers/manager_settings.py), [manager_storefront_settings.py](../../routers/manager_storefront_settings.py), [manager_auth.py](../../routers/manager_auth.py), [доступ](authentication.md#manager) |

## Где смотреть актуальный контракт

- В запущенном локальном API: `http://localhost:8000/docs` и
  `http://localhost:8000/openapi.json`. На сервере используйте его собственный
  origin и сверяйте версию запущенного релиза. Сохранённый [openapi.json](../../openapi.json)
  обновляется вместе с изменениями HTTP-схемы по
  [процедуре разработки](../development-workflow.md#verification-by-change).
- HTTP-маршруты и Pydantic response/request models задают фактические поля.
  OpenAPI перечисляет их для FastAPI-маршрутов, но не описывает всю проверку
  запроса во внешнем middleware. Например, подписанные заголовки витрины
  намеренно отсутствуют в схеме: их контракт —
  [storefront-context-contract.md](../storefront-context-contract.md#required-signed-headers).
- MCP монтируется как отдельный ASGI-маршрут при `CONNECTOR_ENABLED=true`,
  поэтому `/api/connector/mcp` отсутствует в OpenAPI. Список и входные/выходные
  схемы инструментов клиент получает через MCP `tools/list`; текущий исходный
  каталог — [connector_mcp_tools.py](../../services/connector_mcp_tools.py).
  [Handoff](../chatgpt-connector-handoff.md#что-выпущено-и-можно-подключать)
  описывает границы первого выпуска.
- Схема называется `Kitlane / MVN HTTP API`; существующее `info.version=0.1.0`
  оставлено как метаданные схемы. Это не обещание версии всего бизнес-контракта.
  Префикс `v1` есть у публичной витрины и внутреннего бота; Manager не имеет версии в URL. Совместимость изменений
  проверяйте по конкретному клиенту и релизу, а не по общему полю `info.version`.

Для поиска нужной операции без вывода всего большого OpenAPI запустите локальный
API и выполните:

```bash
curl -fsS http://localhost:8000/openapi.json | python3 -c 'import json,sys; p=json.load(sys.stdin); print("\n".join(sorted(x for x in p["paths"] if x.startswith("/api/v1/products"))))'
```

Проверка каталога только читает локальные данные. Она предполагает запущенный
API и локальную базу по [инструкции разработки](../development-workflow.md#environment-and-app):

```bash
curl -fsS http://localhost:8000/api/health
curl -fsS 'http://localhost:8000/api/v1/products?page=1&limit=5'
curl -fsS http://localhost:8000/api/v1/filters/config
```

`localhost` разрешён в стандартной конфигурации. Если окружение требует
подпись всех запросов витрины, последние два вызова получат `401`; следуйте
[серверному контракту подписи](../storefront-context-contract.md#resolution-and-compatibility),
не переносите ключ подписи в браузер или этот документ.

## Как читать ответы и делать повторы

У семейств API разные правила. Для `page`, `limit`, фильтров, ошибок,
`Idempotency-Key`, `Retry-After` и версий записей откройте
[соглашения HTTP](conventions.md). Для схемы входа и сроков действия токенов —
[авторизацию](authentication.md). Перед вызовом мутации найдите именно её
request/response, права и исключения: универсального правила повторять все
`POST` или единого формата ошибок для всей платформы нет.

## Как поддерживать контракт при развитии API

[Инвентаризация и критерии готовности](documentation-coverage.md) фиксируют
точный перечень 609 HTTP-операций и завершённые этапы проверки по областям.
Непустой `description` сам по себе не означает полноту контракта.

- Для новой или изменённой операции описывайте назначение, права и область
  данных, ограничения параметров, ошибки и безопасный повтор рядом с маршрутом
  и его моделями. Автоматического summary из имени Python-функции недостаточно
  для партнёрской интеграции.
- Обновляйте [перечень операций](operation-inventory.json) после проверки кода:
  у каждой операции должны быть description и ссылка на этап проверки.
  Unit-проверка обнаруживает потерю описания, новую/удалённую операцию и смену
  operation ID; правильность смысла остаётся предметом ревью.
- При изменении HTTP-схемы обновляйте OpenAPI и сгенерированный Manager-клиент
  по [процедуре проверки](../development-workflow.md#verification-by-change).
  При изменении бизнес-смысла или авторизации обновляйте профильный контракт
  даже тогда, когда форма JSON осталась прежней.
- Новую поверхность добавляйте в матрицу потребителей и карту областей выше.
  Поля и типы храните в схемах, подробные правила — в одном профильном документе;
  этот указатель связывает их и не дублирует все операции.

## Граница будущей интеграции поставщика

Внутренние маршруты [manager_supply.py](../../routers/manager_supply.py) и
[manager_supplier_mapping.py](../../routers/manager_supplier_mapping.py)
позволяют сотрудникам вести поставщиков, источники, предложения и привязки.
Их операции перечислены среди глобальных платформенных разрешений в
[manager_permission_policy.py](../../routers/manager_permission_policy.py).
Ни Manager JWT, ни токен бота, ни личный OAuth grant ChatGPT не являются
учётными данными поставщика. Доступ к этим маршрутам не следует выдавать
внешнему партнёру.

Перед прототипом отдельного supplier-контракта используйте
[границы и решения интеграции](supplier-integration-boundary.md): там перечислены
существующие возможности, ограничения и вопросы, которые нужно закрыть до
выдачи доступа. Документ не определяет реализованный партнёрский протокол.
