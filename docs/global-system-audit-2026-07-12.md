# Глобальный аудит MVN перед разделением на сервисы

Дата среза: 2026-07-12
Последнее обновление статусов: 2026-07-13
Базовый commit: `721bae2e` (`origin/main`)
Статус документа: живой реестр; поле `Статус` обновляется по мере закрытия волн.

## 1. Итог

MVN уже состоит из нескольких независимо разворачиваемых процессов — API, Astro/Vue storefront, Vue manager и Telegram bot — но внутри backend пока остаётся распределённым монолитом с общей БД, неявными правами, локальными in-memory job'ами и сетевыми побочными эффектами внутри HTTP-транзакций.

Физическое разделение сейчас не уменьшит сложность. Оно превратит локальные проблемы в распределённые: потерянные обновления станут конфликтами между сервисами, недолговечные `asyncio.create_task` — потерянными очередями, а прямые вызовы Telegram/SMTP/Google — несогласованными saga без восстановления.

Правильная последовательность:

1. Закрыть эксплуатационные и security-блокеры.
2. Ввести явные domain boundaries внутри текущего приложения.
3. Добавить optimistic concurrency, outbox/inbox, идемпотентность, durable jobs и аудит действий.
4. Стабилизировать lean DTO и versioned contracts.
5. Только затем выносить ранние кандидаты: media processing, communications, documents и supplier ingest.

## 2. Как проверяли

- Статический проход по Python, SQLModel/SQLAlchemy, FastAPI router/service/CRUD boundaries.
- Отдельные аудиты `manager_frontend`, `web`, `bot_app` и notification path.
- Поиск монолитов, транзакционных границ, in-memory state, blocking I/O и неограниченных загрузок.
- Проверка CI, Alembic, OpenAPI/codegen и тестовой архитектуры.
- Исходный baseline unit suite: **892 passed**; финальный snapshot Wave 0: **996 passed**.
- Manager: финальный `vue-tsc -b` и production build после RBAC/codegen прошли.
- Storefront: финальные brand/homepage/catalog/cart/SEO/pricing/theme tests прошли; full-data build создал **797 pages**, включая все **740 из 740** опубликованных product routes тестового production-like среза.
- `pip-audit`: 96 advisory records в 18 Python packages.
- `bandit`: 7 high, 7 medium; каждое high finding перепроверяется вручную, потому что часть результатов контекстна.
- `ruff`: 135 diagnostics; среди false positives найден реальный undefined variable в Onliner parser.
- Точечные production HTTP-измерения каталога без изменения данных.
- Локальные application logs использовались только как доказательство delivery failures; секреты и Telegram IDs в документ не включены.

## 3. Шкала

- **P0** — немедленный риск потери/искажения данных, захвата привилегий или разрушительной операции; блокирует декомпозицию и release.
- **P1** — подтверждённый высокий риск безопасности, надёжности, корректности или масштабирования; закрыть до extraction.
- **P2** — существенный долг, который уже создаёт деградацию или резко удорожит дальнейшее развитие.
- **P3** — локальное качество и упрощение после стабилизации критического пути.

## 4. Единый реестр P0/P1

| ID | Приоритет | Контур | Подтверждённая проблема | Статус |
|---|---:|---|---|---|
| SEC-001 | P0 | API/Manager | Любой active staff, включая installer/repair, получает полный manager API; роль извлекается, но не проверяется | Закрыто в Wave 0 |
| OPS-001 | P0 | Backup | Destructive restore доступен обычному staff, lock/status process-local; `psql` может продолжить после SQL error, media replacement неатомарна | Частично: owner-only, default-off, fail-fast и atomic media swap; distributed control plane открыт |
| ORD-001 | P0 | Checkout | Browser управляет `quantity` и `installation_price`; отрицательные/огромные значения проходят и влияют на CRM total | Закрыто в Wave 0: bounds + серверный расчёт; idempotency остаётся в DATA-002/WEB-004 |
| AUTH-001 | P1 | Auth | Telegram login принимает вычислимую HMAC-подпись при пустом `BOT_TOKEN` | Закрыто в Wave 0 |
| AUTH-002 | P1 | Auth | Нет rate limit/lockout; пароль допускается от 6 символов, JWT живёт 7 дней, legacy admin нельзя отозвать | Открыто |
| AUTH-003 | P1 | Google | OAuth callback без auth/state может заменить общий Drive account | Закрыто в Wave 0 |
| DATA-001 | P1 | Orders | Нет version/ETag; полный snapshot из drawer молча затирает параллельные изменения | Открыто |
| DATA-002 | P1 | Customers | Неединая нормализация телефона и race find-or-create создают дубликаты; checkout не имеет idempotency key | Открыто |
| JOB-001 | P1 | Runtime | Backup, restore, email import и часть catalog jobs используют память процесса и `create_task` | Открыто |
| JOB-002 | P1 | Media | Два worker'а могут атомарно незащищённо забрать одну media job | Закрыто и развернуто в API Wave 0: atomic claim, lease token, heartbeat; сам worker остаётся выключен до отдельного managed rollout |
| COM-001 | P1 | Telegram | Ошибки проглатываются, попытка считается доставкой; живой log доказал ложный `notified_admins=2` при отказе | Закрыто в Wave 0 |
| COM-002 | P1 | Telegram | Ручной bank import не вызывает notify, после dedupe уведомление теряется навсегда | Закрыто в Wave 0 |
| COM-003 | P1 | Telegram/Email | Нет transactional outbox: события теряются/дублируются, внешние вызовы блокируют HTTP transaction | В работе: additive outbox/inbox/per-recipient delivery foundation реализуется в Wave 1 PR-A; producer switch и consumer ещё открыты |
| COM-004 | P1 | Tests | Integration checkout способен отправлять реальные Telegram-сообщения владельцам | Закрыто в Wave 0 |
| PRIV-001 | P1 | Media | Реквизиты, order attachments и диагностические фото лежат в публичном `/media`/public R2 | Открыто |
| WEB-001 | P1 | SSG | Build запрашивает только 1000 из 1117 товаров; product routes после 1000 отсутствуют и production URL отвечает 404 | Закрыто в Wave 0: пагинация, dedupe и hard-fail invariant |
| WEB-002 | P1 | Public API | `/api/v1/config` и catalog DTO раскрывают internal config, hidden tags, supplier price/markup metadata | Частично: public config allowlist закрыт; отдельные lean DTO ещё открыты |
| WEB-003 | P1 | SEO | JSON-LD считает отсутствующий товар `InStock`; raw `JSON.stringify` допускает `</script>` stored-XSS surface | Закрыто в Wave 0: единый safe JSON-LD и availability policy |
| WEB-004 | P1 | Abuse | Orders/leads/repair-AI/proxy endpoints не имеют rate limit, idempotency и anti-bot controls | Открыто; dedicated contact-lead command не заменяет rate limit/dedupe |
| PERF-001 | P1 | Catalog | Public `limit=1000` отдаёт около 5.4 MB и допускается API; SSG зависит от этого amplification path | Закрыто в Wave 0: public cap 100 + paginated SSG |
| PERF-002 | P1 | Catalog | Search count не применяет search filter: 0 items при `meta.total=1117` подтверждено production response | Закрыто в Wave 0 |
| PERF-003 | P1 | Manager media | Одна страница media может сделать ~360 count queries + 40 full series scans | Закрыто в Wave 0: SQL pagination/filtering и batch usage (4 queries) |
| PERF-004 | P1 | Manager | Orders/Leads скачивают все страницы; list DTO тащит полный object graph | Открыто |
| PERF-005 | P1 | Async API | Blocking SMTP и Google SDK выполняются внутри async request path | Открыто |
| PERF-006 | P1 | Uploads | Несколько upload paths читают целые файлы в RAM до проверки размера | Частично: media worker/repair bounds усилены; единая streaming policy открыта |
| SUPPLY-001 | P1 | Dependencies | Python audit: 96 advisory records/18 packages; manager lock: 1 critical, 3 high, 3 moderate | Открыто; parser/TLS hardening не закрывает dependency advisories |
| CI-001 | P1 | CI/Data | Тесты создают schema через metadata и не проверяют Alembic upgrade; сломанная migration может пройти CI | Закрыто в Wave 0: baseline migration + empty-DB upgrade/check в CI; локальный replay до `2d4f6a8b0c13` и `alembic check` прошли |

## 5. API/backend

### 5.1 Права и destructive operations

На исходном срезе роли были объявлены в `services/staff_user_service.py`, но `core/security.py:get_current_user` возвращал только username, а большинство manager/system/admin router'ов не превращали роль в политику доступа. Wave 0 ввела manager/owner dependencies и negative RBAC tests: installer исключён из manager API, а staff, raw settings, backup/restore и Google OAuth ограничены owner. UI скрывает owner-only разделы, но API остаётся authoritative enforcement.

Минимальная безопасная модель:

- `manager.read/write` — owner/manager;
- `staff.manage`, `credentials.manage`, `backup.restore`, `system.configure` — owner;
- destructive operations требуют recent re-auth и audit record;
- UI capabilities используются только для отображения, решение всегда принимает API;
- legacy env admin временно считается emergency owner с отдельной метрикой и планом удаления.

Restore нельзя считать обычной product-функцией. Текущему процессу не хватает maintenance mode, distributed fencing, доказательства active primary, traffic drain, durable operation record и rollback/recovery runbook. Даже после RBAC restore должен быть выключен по умолчанию до появления control-plane workflow. `psql` необходимо запускать как минимум с `ON_ERROR_STOP` и transactional/verified semantics, применимыми к формату dump.

### 5.2 Checkout и целостность заказа

На исходном срезе `schemas.py:CartItemPayload` не ограничивал quantity/price/items. `OrderService.create_from_website` брал product price из БД, но installation price и quantity — из браузера. Это позволяло искажённой сумме попасть в CRM snapshot, документы и уведомления.

Wave 0 закрыла именно этот P0: ввела bounds для заказа и строк, проверку непустой корзины, серверный расчёт монтажа по тарифу/options и versioned pricing snapshot; клиентская цена теперь только hint для telemetry. Idempotency public command, canonical customer identity и атомарная запись order+outbox остаются Wave 1 и не считаются закрытыми этим калькулятором.

После Wave 0 остаются:

- canonical phone identity и race-safe customer get-or-create;
- idempotency key на public command;
- одна транзакция для customer/order/lines/outbox event.

### 5.3 Транзакции и связанность

В `services/` найдено около 170 прямых `session.commit()`. Сервисный метод сам решает границу транзакции, поэтому orchestration часто не может атомарно изменить domain state и записать событие. `OrderService` напрямую зависит от Bot, Google, documents и staff services; public read service импортирует manager-oriented logic.

Перед extraction нужен application/unit-of-work слой:

- domain methods не выполняют внешние сетевые вызовы;
- command handler владеет одной транзакцией;
- outbox event сохраняется в той же транзакции;
- provider worker работает после commit;
- downstream consumer имеет inbox/idempotency.

### 5.4 Durable jobs

Process-local locks безопасны только при единственном вечном процессе. В blue/green и HA окружении это условие уже неверно. Общий job contract должен включать status, attempt, lease owner/token, lease expiry, heartbeat, input/output references, idempotency key, error class и timestamps. Claim — atomic `UPDATE ... RETURNING` или `FOR UPDATE SKIP LOCKED`; complete/fail обязаны проверять lease token.

Для media jobs этот минимальный контракт реализован в Wave 0: PostgreSQL claim использует locking/conditional update, complete/fail проверяют worker+token+lease, worker продлевает lease heartbeat'ом. Это закрывает JOB-002 в коде, но не заменяет общий durable job framework из JOB-001 и требует совместимого rollout без смешивания старого worker с новым API.

### 5.5 Протокол rollout media worker

1. **Stop/drain:** остановить polling/claim на всех старых workers, дать уже взятым jobs завершиться и подтвердить, что нет `running` jobs; зависшие jobs не «перехватывать» вручную, а дождаться lease policy/requeue.
2. **Migrate + API:** выполнить additive migration с `lease_token`, затем развернуть API с claim/renew/complete/fail contract. Пока новый API не подтверждён health/smoke checks, workers остаются остановлены.
3. **Workers:** развернуть новую версию worker на всех узлах. Она обязана получать token из claim, продлевать lease и передавать token в complete/fail.
4. **Resume:** запустить один worker, проверить одну тестовую job и отсутствие duplicate claim/expired lease; после этого вернуть штатную concurrency.

Старый worker несовместим с новым обязательным lease contract, поэтому mixed-version period запрещён. Rollback начинается с повторной остановки workers: активные jobs завершаются под новой парой API/worker либо после истечения lease безопасно requeue'ятся. Затем API и worker откатываются как единая совместимая пара. Additive колонку `lease_token` во время инцидента не удалять и migration не downgrade'ить; старую пару разрешено включать только после проверки, что tokenized `running` jobs отсутствуют. Если сбой произошёл до resume, оставить очередь остановленной и восстановить API/БД по release runbook до обработки jobs.

### 5.6 Security toolchain

Подтверждённые ручной проверкой классы:

- `verify=False` в supplier parsers/price integration — риск подмены каталога;
- remote/user XML через stdlib ElementTree — заменить на hardened parser для недоверенных источников;
- configurable media command через `shell=True` — перейти на argv contract без shell interpolation;
- tar validation проверяет traversal/symlink, но должна явно отклонять device/FIFO/special entries;
- реальные dependency advisories требуют coordinated upgrade + full regression, а не слепого pin bump.

Wave 0 уже убрала все обнаруженные `verify=False`, перевела configurable image command с shell-string на argv без shell, добавила hardened XML parser для supplier/XLSX/SVG и ограничила XLSX/tar archive expansion. Dependency advisory upgrade остаётся отдельной волной.

## 6. Manager Vue + manager API

### 6.1 Потерянные обновления

`OrderEditDrawer.vue` отправляет почти полный snapshot. Backend заменяет product/service lines без `version`. Два менеджера или manager+bot могут сохранить разные части заказа; последний silently возвращает старые данные.

Целевая модель:

- integer `version` у aggregate;
- conditional update `WHERE id=? AND version=?`;
- HTTP 409 с current version и changed fields;
- отдельные commands для status, payment, lines, customer, schedule;
- UI показывает conflict/reload/merge, а не молча повторяет save.

### 6.2 Media library

На исходном срезе `MediaLibraryService.list_assets` materialize'ил таблицу, фильтровал tags и пагинировал в Python. Для каждого item отдельно считался usage девятью запросами и перечитывались series. Wave 0 перенесла filtering/count/pagination в SQL и свела usage страницы к batch aggregation (4 запроса вместо порядка 360). Нормализованный `media_reference`, backfill/dual-write и lazy usage details остаются следующей волной.

### 6.3 UI loading model

Orders и Leads последовательно забирают все страницы при каждом refresh/save/filter. Это маскирует отсутствие server-side board/list projection. Нужны slim DTO, cursor pagination, summary counts, server filters и virtualized rendering.

### 6.4 Монолиты и safety net

Крупнейшие manager файлы:

- `OrderEditDrawer.vue` — 4023 строки;
- `ProductsView.vue` — 2570;
- `CustomerProfileView.vue` — 2210;
- `ProductEditModal.vue` — 2026;
- `BrandsView.vue` — 1911;
- `SettingsView.vue` — 1831;
- `OrderDocumentsPanel.vue` — 1749;
- ручной `api.ts` façade — 1264.

В manager frontend нет component/unit tests и lint command; CI фактически проверяет build/codegen. В Wave 0 статическая навигация уже вынесена из `App.vue`, который уменьшился с 751 до 671 строки без изменения поведения. Остальное разделение начинать не по размеру шаблона, а по use case/state ownership: order lines, payment, schedule, documents, customer, assignments. Для каждого composable/state machine сначала добавить Vitest, для critical flows — Playwright.

### 6.5 Остальные подтверждённые риски

- Products search/load-more stale response race закрыт в Wave 0 request-generation/abort guard'ом; этот guard нужно сохранять при декомпозиции view.
- Google Docs/Contracts меняет remote state до DB commit и не везде компенсирует failure.
- Brand-series GET выполняет auto-sync, commit и cache purge; GET должен быть чистым.
- Supply UI отмечает request отправленным до успешного clipboard/send action.
- Default branch/document numbering invariants не полностью защищены DB constraints/locks.
- Часть OpenAPI success responses деградирует до `{}`/`any`.

## 7. Storefront Astro/Vue + public API

### 7.1 SSG completeness

На исходном срезе `web/src/utils/api.js` запрашивал `limit=1000`. API содержал 1117 published products, а prod-data build создавал ровно 1000 product HTML pages. Первый slug за пределом лимита отсутствовал в `dist`, production URL вернул 404.

Wave 0 реализовала paginated manifest fetch с dedupe/count/missing invariants и hard failure, а public API cap снизила до 100. Это закрывает подтверждённый пропуск routes; финальный production-like build после последних storefront-изменений прошёл с 797 страницами и всеми 740/740 product routes тестового среза.

Реализованный в Wave 0 контракт:

- paginated manifest fetch до `meta.pages`;
- build invariant: fetched unique slugs == API total;
- duplicate/missing slug — hard failure;
- public API cap <=100 после миграции build path.

### 7.2 DTO и payload

На исходном срезе public config возвращал весь `GlobalConfig`, включая supplier/mail/catalog operational state. Wave 0 добавила явный allowlist публичных ключей. Catalog list по-прежнему использует слишком широкий detail payload со specs/hidden tags/internal price metadata, поэтому WEB-002 закрыт только частично.

Нужны allowlisted `PublicSiteConfig`, `CatalogCard`, `ProductDetail`, `BuildManifest` и `FilterConfig` DTO. Public mapper должен быть отдельным от manager model. Catalog card содержит только поля, реально нужные карточке; internal tags/specs/prices не должны фильтроваться на клиенте.

Измерения с текущего контура:

- catalog `limit=1000`: около 5.4 MB, TTFB ~2.4 s, полный ответ ~3.0 s;
- catalog HTML около 1.15 MB raw, Wi-Fi route ~1.36 MB;
- brand pages доходят примерно до 2 MB raw;
- до 120 отдельных price toggle islands на странице.

### 7.3 SEO и XSS

- На исходном срезе Product JSON-LD всегда выставлял `InStock`, независимо от реальной availability.
- На исходном срезе query-filter pages отдавали default static canonical/H1 до client JS.
- На исходном срезе `set:html={JSON.stringify(schema)}` не экранировал `<`; строка `</script>` из product/import content могла закрыть JSON-LD script.

Wave 0 добавила единый `safeJsonLd` (`<` -> `\u003c` и экранирование опасных separators), общий availability mapper, noindex/sitemap policy для transactional/query surfaces и тесты на отсутствующий товар/`</script>`. Дальнейшая оптимизация SEO assembly относится к модульному рефакторингу, а подтверждённые WEB-003 defects закрыты.

### 7.4 Public abuse surface

Checkout, contact/availability leads, repair upload/AI и proxies не имеют согласованной edge+app quota. Wave 0 отделила обычную contact form от создания пустого заказа и теперь сохраняет её как настоящий `Lead`, но это только корректная domain-команда, а не защита от abuse. Wave 1 должна добавить rate limit на edge и в приложении, anti-bot по risk score, idempotency key, canonical phone/email identity и dedupe window для повторных public leads. Для repair дополнительно нужны aggregate streaming limit, MIME/magic/decode validation и durable background job.

### 7.5 Frontend monoliths

Крупнейшие storefront файлы: product page ~2145 строк, `CatalogApp.vue` ~2096, `InstallationCalculator.vue` ~1016, `PriceWithToggle.vue` ~989, `CheckoutForm.vue` ~841. Astro/Vue ProductCard logic дублируется. После lean DTO разделить query state, catalog results, card pricing, checkout command и SEO assembly. Wave 0 уже добавила в `CatalogApp` AbortController/request generation для защиты от stale fetch; это локальный safety fix, не завершённый рефакторинг монолита.

## 8. Telegram bot и communications

### 8.1 Delivery contract

На исходном срезе `BotService.send_message` глотал provider error, а callers увеличивали `sent_count` после любой попытки. В локальном operational log найдено пять реальных отказов, включая обоих текущих owners; рядом scheduler заявил двух уведомлённых. Это был доказанный false-success, а не теоретическая ветка.

Wave 0 перевела текущий контракт на подтверждённый `bool`, сделала partial fan-out видимым и сохранила multi-recipient delivery; ручной bank import теперь также уведомляет. Полный structured `DeliveryResult` с provider message ID/error code/retry-after и durable retry queue остаётся частью Communications/outbox.

### 8.2 Outbox

Сейчас часть send происходит после commit, поэтому crash теряет событие; часть installer send — до commit, поэтому rollback создаёт фантомное уведомление. SMTP имеет ту же двойственность и блокирует event loop.

Минимальные события:

- `website_order.created`;
- `product_availability.requested`;
- `repair_lead.created`;
- `bank_receipt.imported`;
- `email_lead.created`;
- `installer.assigned`;
- `work_stage.status_changed`.

Delivery uniqueness: `(event_id, channel, recipient_id, template_version)`. Worker: `SKIP LOCKED`, backoff+jitter, Telegram `retry_after`, terminal blocked/403, chunking, fallback, DLQ, queue-age/delivery metrics.

### 8.3 Access и privacy

- Empty `BOT_TOKEN` login теперь fail closed и покрыт тестом.
- DB должна стать authoritative access source; `ADMIN_IDS` — только явно включаемый emergency mode с TTL/audit.
- Customer/user HTML всегда проходит renderer/escaping/length policy.
- Bot/order/requisites attachments должны перейти в private storage с signed access и retention.
- AI/OCR отправка PII/банковских данных требует data classification, minimization, vendor policy и feature flags.
- FSM data требует TTL и явного clear.

### 8.4 Bot monoliths

`bot_app/handlers/admin.py` — ~1658 строк, смешивает UI, auth, download, OCR, requisites, repair, warranty и product mutation. Сначала разнести handlers по use cases и оставить единый CRM application API. Сам inbound bot gateway выносить позже notification delivery; прямой доступ отдельного сервиса к общей БД запрещён.

## 9. Сквозные P2

### Наблюдаемость

- Wave 0 добавила/валидирует HTTP `X-Request-ID` и прокидывает его в logging context; сквозного event correlation до workers ещё нет.
- Нет Prometheus/OpenTelemetry; manager telemetry — process-local deque.
- Sentry traces ограничены конфигом (default 10%, profiles 0), request bodies/PII/frame locals выключены; event и transaction scrubber удаляет headers/query/cookies/secrets и Telegram token URLs.
- Глобальные exception logs больше не пишут traceback/query; domain-specific logs всё ещё требуют последовательной data-classification ревизии.
- Нет durable audit trail для staff roles/passwords, OAuth, restore, payments и destructive catalog changes.

### Catalog/search

- Ошибка `count_filtered` без smart-search filter закрыта в Wave 0 и покрыта тестом.
- `specs/keys` materialize'ит published specs на каждый request.
- JSON/EXISTS recommended filters не имеют отдельного read model.
- Public cache headers отсутствуют, Cloudflare отвечает dynamic, хотя revision/purge mechanism уже есть.
- Перед добавлением индексов нужно снять production `EXPLAIN` и проверить реальные indexes, а не полагаться только на SQLModel declarations.

### Parsers/import

- Onliner parser с undefined `title` исправлен и покрыт regression test.
- Importer имеет широкую связанность с parsers, media, catalog и supplier logic.
- Все найденные supplier `verify=False` удалены; remote XML/XLSX/SVG переведены на hardened parsing и archive bounds.
- Import сначала оформить как durable inbox/job с raw source snapshot и idempotent apply.

### CI/tests

- Integration fixture делает `drop_all/create_all` на каждый test: медленно и скрывает migration defects.
- Empty-DB `alembic upgrade head` + `alembic check` добавлен в CI; локальный replay текущего head `2d4f6a8b0c13` прошёл без schema drift, upgrade-from-supported-version coverage ещё нужно расширять.
- Добавить Ruff с осмысленными SQLModel exceptions, Bandit triage baseline, `pip-audit`, frontend audit, Renovate/Dependabot.
- В тестах запретить внешний network egress по умолчанию и явно включать fake providers.

## 10. Что уже хорошо

- Router/service boundary в большинстве manager endpoints соблюдается.
- OpenAPI client генерируется и проверяется на drift.
- Catalog revision/purge и persisted catalog import дают основу для read model/build manifest.
- Media processing имеет job abstraction, усиленную в Wave 0 atomic claim, lease token и heartbeat.
- Document generation местами уже делает compensation cleanup.
- Orders/Leads имеют request guards для части full reload scenarios.
- HA/PITR/runbook дисциплина заметно сильнее типичного монолита.

Проект не нужно переписывать. Нужно укрепить эти существующие seams и убрать обходы вокруг них.

## 11. Волны исправлений

### Wave 0 — немедленная защита

- RBAC manager/owner и защита destructive endpoints.
- Telegram fail-closed, честный delivery result, test network isolation, manual bank notify.
- Checkout input bounds и server-authoritative installation quote foundation.
- Restore default-off/fenced guard и `psql` fail-fast.
- Google OAuth state/owner-only/configured redirect.
- SSG completeness, search count, JSON-LD availability/XSS.
- Public config allowlist и cap amplification path после SSG pagination.
- Atomic media claim с lease token/heartbeat и безопасным rollout protocol.
- Migration baseline и empty-DB Alembic gate в CI.
- Dependency advisories только инвентаризированы и triage'нуты; coordinated upgrade ещё не выполнен.

### Wave 0 — ledger на текущем snapshot

Wave 0 слита через PR #726 и развернута в production как immutable SHA `886593e0`. Backend migration/blue-green primary/fenced replica, frontend canary/atomic VPS/Cloudflare smoke, последующие replication и HA invariant checks прошли. Это не закрывает явно перенесённые в Wave 1–2 риски. Фактические проверки:

| Gate | Результат | Статус |
|---|---|---|
| Полный unit suite | **996 passed** после финальных RBAC/observability правок | Пройден |
| Полный integration suite | **181 passed**; последующие settings/observability изменения дополнительно покрыты **62 scoped tests** | Пройден |
| Manager typecheck/build | `vue-tsc -b` + production Vite build после RBAC и codegen | Пройден |
| Storefront tests/build | Все scoped Node/theme tests; production-like API: **740 products**, build: **797 pages**, **740/740 product routes** | Пройден |
| Alembic upgrade/check на clone существующей БД | Пройден на текущей цепочке migrations | Пройден |
| Fresh empty-DB replay до текущего `head` + `alembic check` | Полная цепочка до `2d4f6a8b0c13`; `No new upgrade operations detected` | Пройден |
| Единый GitHub CI после исправления Linux module collision | **1177 passed**, migration и codegen gates зелёные | Пройден |
| Production deploy/smoke | Patroni migration + primary/replica deploy, Cloudflare/VPS storefront smoke, live API DB online | Пройден |

Wave 0 подтверждена локально, в CI и production. Media processing worker намеренно не активирован: в production нет worker unit/container/token и очередь пуста; его первое включение остаётся отдельным canary rollout только новой версии. Открытые DATA/JOB/COM/PRIV/WEB/PERF/SUPPLY пункты переходят в Wave 1–2.

### Wave 1 — данные и надёжность

- Transactional outbox/inbox + communications worker. PR-A добавляет только выключенный additive persistence/contracts foundation; переключение producers и consumer выполняются следующими отдельными PR.
- Order version/409 и command-specific updates.
- Canonical customer identity + checkout idempotency.
- Public contact/availability lead abuse policy: edge+app rate limit, canonical phone/email, dedupe window, idempotency key и risk-based anti-bot.
- Общий durable job framework для backup/email/catalog operations поверх уже защищённого media claim.
- Private attachments и единая streaming upload policy.
- Нормализованный `media_reference`; slim manager/public DTO; server pagination для Orders/Leads.
- Upgrade-from-supported-version migration tests, coordinated dependency upgrades и полный external-provider egress guard.

### Wave 2 — модульный монолит

- Разделить `OrderService`, manager drawers/views, storefront catalog/product/checkout и bot handlers по use cases.
- Ввести domain-owned repositories/application commands; убрать cross-domain table writes.
- Documents/Google saga, supplier inbox, catalog read model/cache.
- Audit trail, correlation IDs, metrics/SLO, provider dashboards.

### Wave 3 — физическое выделение

1. Media processing worker/service.
2. Notification delivery service.
3. Documents worker/service.
4. Supplier ingest service.
5. Storefront read BFF/cache, если подтверждена отдельная нагрузка.

CRM Core и Catalog Core разделять последними и только по измеренной нагрузке/ownership, а не ради самого факта микросервисов.

## 12. Definition of done до первого extraction

- Нет открытых P0; согласованный список допустимых P1.
- Backend permission matrix покрыта negative tests.
- Все public commands имеют bounds/rate/idempotency policy.
- Ни один business request не зависит от синхронной доставки Telegram/SMTP/Google.
- Durable jobs переживают restart и multi-worker claim.
- Order/customer critical writes имеют concurrency contract.
- Public/manager DTO разделены и contract-tested.
- Migration upgrade проверяется CI.
- Request/event correlation проходит от edge до worker.
- Каждый domain имеет владельца таблиц и запрет чужих прямых writes.
- Extraction не требует shared database writes со стороны нового сервиса.
