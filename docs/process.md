# Процессы и поддержка

В этом документе описаны регулярные процессы обслуживания проекта.

## Git-процесс

Для безопасной командной работы используйте процесс из документа:

- `docs/git-workflow.md`

## Manager-first policy (active)

1. Main product development target:
   - `manager_frontend/` + `routers/manager_*`.
2. Legacy SQLAdmin target:
   - compatibility and maintenance only.
   - allowed: bugfixes, regressions, required compat updates.
   - disallowed by default: net-new product workflows/features.
3. Any PR touching `admin/*` must include justification:
   - why legacy change is required now,
   - why this is not implemented in manager flow.

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
