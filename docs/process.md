# Процессы и поддержка

В этом документе описаны регулярные процессы обслуживания проекта.

## Git-процесс

Для безопасной командной работы используйте процесс из документа:

- `docs/git-workflow.md`

## Manager-first policy (active)

1. Main product development target:
   - `manager_frontend/` + `routers/manager_*`.
2. Legacy SQLAdmin status:
   - removed from the application.
   - `/admin` is kept only as a redirect into Manager UI.
   - do not reintroduce SQLAdmin or add legacy `/admin` UI workflows.
3. Any new internal workflow must target manager routes and manager UI.

## Static Content Image Workflow

Use `docs/content-image-assets.md` for static storefront images committed under
`web/public/img`:

- optimize new blog/service/hero/brand images with `cd web && npm run image:content`;
- audit existing committed rasters with `cd web && npm run image:audit`;
- keep catalog product uploads and product gallery variants in the backend
  media/R2 pipeline, not this static content workflow.

## Manager API Client Sync Policy

When changing manager API contracts (`routers/manager_*`, `schemas.py`, OpenAPI-affecting dependencies):

1. Regenerate OpenAPI schema:
   - `python3 scripts/legacy/extract_openapi.py`
2. Regenerate typed manager client:
   - `cd manager_frontend && npm run gen:api`
3. Validate manager build:
   - `cd manager_frontend && npm run build`
4. Commit updated artifacts when changed:
   - `openapi.json`
   - `manager_frontend/src/client/*`

CI enforces this sync and fails if generated artifacts differ from committed files.

## Manager CRM Data Source Rules

1. For lead qualification and customer-card hydration, use:
   - `GET /api/manager/customers/{customer_id}` as source of truth for full requisites.
2. `/api/manager/customers` list endpoint is for list/search UX and may contain partial snapshots.
3. Any manager flow that edits/qualifies a customer must prefer detail DTO over list item DTO when both are available.

## API-роутеры после декомпозиции

Основной входной модуль API: `routers/api.py` (компоновщик).

Доменные роутеры:

- `routers/api_products.py` — публичный каталог/товары/specs/filters config.
- `routers/api_orders.py` — публичное создание заказа с сайта.
- `routers/api_content.py` — статьи, услуги, глобальная конфигурация.
- `routers/api_proxy.py` — proxy-эндпоинты ЕГР/банки.
- `routers/api_admin.py` — admin search + health.

Правило поддержки: новую API-функциональность добавляйте в соответствующий доменный роутер, не возвращайте монолит в `routers/api.py`.

## 🛠️ Нормализация характеристик (Specs)

Система автоматически нормализует характеристики при импорте (приводит русские ключи к системным, чистит значения). Однако, при добавлении большого количества новых товаров (например, +100 шт.), могут появиться новые вариации ключей.

### Регламент
Запускать проверку ключей **периодически** или после масшабного добавления товаров в каталог.

### Инструкция

1. **Проанализировать ключи**
   
   Запустите скрипт анализа, чтобы найти новые, "неопознанные" ключи. Он покажет самые частые ненормализованные ключи и предложит варианты исправления.

   ```bash
   docker compose exec app python3 scripts/analyze_spec_keys.py
   ```

2. **Обновить карту ключей**
   
   Если скрипт нашел важные ключи (например, `Минимальная мощность` или `Страна`), добавьте их в файл:
   
   📄 `services/spec_normalizer.py` -> `KEY_MAP`

3. **Применить изменения**
   
   Чтобы "починить" уже загруженные товары, запустите скрипт нормализации. Он пройдет по всей базе и перепишет `specs` с учетом новых правил.

   ```bash
   docker compose exec app python3 scripts/normalize_legacy.py
   ```
