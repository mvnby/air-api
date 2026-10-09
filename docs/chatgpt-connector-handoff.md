# Kitlane / ChatGPT: аудит API и хендоф первого выпуска

Дата: 06.10.2026. Ограниченный аудит по [#1082](https://github.com/mvnby/air-api/issues/1082)
и передача первого полезного выпуска по
[#1087](https://github.com/mvnby/air-api/issues/1087).

Проверенный код: `717f0d9fce0041c4ef4a030ca1a5b4eac281d63f`.
Это снимок результата выпуска, а не утверждение о готовности всех будущих
интеграций. Настройка подключения и эксплуатация описаны в
[chatgpt-connector.md](chatgpt-connector.md).

## Что выпущено и можно подключать

Срез 09.10.2026 по #1087: к исходным 15 инструментам добавлены 13 адаптеров
оборудования, замечаний, приватных фото и подготовки draft актов/предложений.
[Контракт и операторский хендоф](chatgpt-maintenance.md) фиксируют точный список,
новый maintenance scope, проверки и fail-closed фото до подтверждения delivery
hostname клиентским пилотом. Код адаптеров не подтверждает Android или Live.
Ниже сохранён датированный аудит первого выпуска; его исключения для ТО
относятся к исходному срезу, а не к новому каталогу из 28 инструментов.

Дополнение 07.10.2026 к срезу #1084: Manager создаёт связанное уточнение прямо
из входящего; явное поручение сохраняется вместе с intake, повторы не создают
дубль. Квалификация сохраняет `incoming_context` с исходником, временем и
происхождением пожеланий, районом/адресом и предварительным звонком; версия
проверяется до мутации. Это не подтверждение выезда и не бронь. Контракт и
граница MCP scopes — в [Manager и напоминания](chatgpt-connector.md#manager-и-напоминания),
поведенческая проверка — [linked clarification tests](../tests/integration/test_incoming_clarification.py).
Ниже исходный аудит первого выпуска; его пункты linked clarification и
qualification-preservation закрыты этим срезом. Следующий срез #1084 добавляет read-only предложения района и услуги/сценария
после подтверждённого сохранения, ручное применение и versioned correction.
Проверки: [preview unit](../tests/unit/test_incoming_preview.py),
[durable preview flow](../tests/integration/test_incoming_preview_flow.py),
[Manager capture](../manager_frontend/tests/quick-incoming-capture.spec.ts).
Операция GET сохранённого входящего расширена параметром `include_preview`;
новых HTTP-операций нет. Внешний AI и обязательный wizard не добавлены.
Это описание изменения; production-выпуск подтверждается PR/CI/deploy,
реальный мобильный пилот остаётся в #1087. Остальные критерии #1084 не закрывать
без отдельного подтверждения; выбор существующего клиента остаётся на qualification.

| Сценарий | Доступность первого выпуска |
| --- | --- |
| Контекст текущего сотрудника, поиск/карточка клиента и заказа | MCP, только доступные записи; чтение без изменения заказа |
| Записать неполное обращение, прочитать/найти/исправить его | MCP и Manager; исходный текст сохраняется, версия проверяется |
| Создать/прочитать/найти/изменить/завершить/открыть поручение | MCP и Manager; обязательного заказа или срока нет |
| Отменить поручение | Manager; отдельного MCP-инструмента отмены пока нет |
| Напоминание о поручении | Внутри `/manager/tasks`, при загрузке/обновлении списка после указанного времени |
| Отозвать подключение | Личный профиль Manager; следующий tool call снова проверяет доступ |

Внешние уведомления, запись заказа, подтверждение выезда, отправка писем,
акты после ТО и обработка Drive не включены. Пожелание клиента о дате не
является календарной бронью. Backend не вызывает LLM: исходные данные
сохраняются независимо от разбора текста в ChatGPT.

Исходный список из 15 инструментов закреплён в
[connector_mcp_tools.py](../services/connector_mcp_tools.py):
`get_current_context`, `search_customers`, `get_customer`, `search_orders`,
`get_order`, `create_incoming`, `get_incoming`, `list_incoming`,
`update_incoming`, `create_task`, `get_task`, `list_tasks`, `update_task`,
`complete_task`, `reopen_task`. Произвольных HTTP/SQL-инструментов нет.

## Путь команды и границы доверия

| Путь | Авторизация → сервис → хранение | Особенности |
| --- | --- | --- |
| MCP read | [ConnectorMCPApplication](../services/connector_mcp.py) → [ConnectorAuthService](../services/connector_auth_service.py) → [ConnectorQueryService](../services/connector_query_service.py) | Отдельные компактные проекции, проверка tenant/storefront и ID, без legacy repair |
| Incoming write | MCP или [Manager router](../routers/manager_incoming.py) → [IncomingCommandService](../services/incoming_command_service.py) → [LeadCommandService](../services/lead_command_service.py) → Lead / incoming event / receipt | Постоянный исходный текст и metadata; не создаёт заказ или работы |
| Task write | MCP или [Manager router](../routers/manager_personal_tasks.py) → [PersonalTaskService](../services/personal_task_service.py) → [PersonalTask](../models/personal_task.py) | Отдельная сущность TODO; не завершает этап работ по заказу |
| Повторы и атрибуция write | [AuthenticatedCommandService](../services/authenticated_command_service.py) → [PublicWriteIdempotencyService](../services/public_write_idempotency_service.py) + [CommandAuditEvent](../models/command_audit.py) | Fingerprint, actor-scoped key, сохранённый ответ и audit успешной команды в одной транзакции |
| OAuth и отзыв | [connector_auth.py](../routers/connector_auth.py) → ConnectorAuthService → [connector models](../models/connector_auth.py) | PKCE S256, точный callback/resource, хеши токенов, одноразовые code/consent, ротация refresh |

Actor создаётся сервером в [CommandActor.from_auth](../core/command_actor.py),
а не принимается из аргументов ChatGPT. MCP повторно разрешает actor как для
HTTP-запроса, так и для каждого инструмента; initialization не фиксирует права.

| Адаптер / actor | Роль, компания и доступ к объектам |
| --- | --- |
| Manager, именной сотрудник | `owner` / `admin` / `manager`, без требования сменить пароль; tenant/storefront из действующей авторизации |
| ChatGPT, grant именного сотрудника | Те же серверные границы плюс `kitlane:read` и отдельные write scopes; живое членство/роль/версия учётных данных проверяются снова |
| TODO | В своей области видимости — автор или исполнитель; чужие сотрудники и связанные Lead/customer/order/equipment отклоняются сервером |
| Demo | Write запрещён общим command service |
| Staff Telegram | Отдельный внутренний сервисный контракт и runtime; bot secret не используется как делегированная MCP-авторизация |

Граница Telegram описана в [bot-service-boundary.md](bot-service-boundary.md).
Наличие system tenant у внутреннего бота само по себе не доказывает уязвимость.
Этот аудит не подтверждает одинаковую семантику всех старых bot-команд:
новый MCP использует выбранные общие сервисы, без изменения bot runtime.

## Повторы, ошибки и восстановление

- Одинаковые actor/tenant/operation/key и payload возвращают сохранённый
  результат; другой payload с тем же ключом даёт явный конфликт.
- После потери ответа после commit повторять тот же payload и ключ. Новый ключ
  означает новую намеренную команду. Для входящего дополнительно используется
  `source_event_id`; изменение содержания события не считается безусловным retry.
- Update требует `expected_version`; при конфликте сначала прочитать актуальную
  запись. У входящих пропущенные поля сохраняются, явный `null` очищает поле.
- Запись, receipt и успешный audit транзакционны. Ошибки и replay отражаются в
  структурированном журнале с actor/channel/tenant/storefront/operation/request;
  исходный текст, пароль и токены в него не пишутся. Это не универсальная
  гарантия аудита всех старых endpoint или durable-журнал всех неуспешных попыток.
- Источник обращения, TODO и receipts хранятся в PostgreSQL, а не в TTL/FSM или
  браузере. Перезапуск процесса не является сроком их хранения. Физический
  production restart ради проверки сохранности пользовательских данных не делали.
- Относительная дата входящего считается от `source_occurred_at` и timezone.
  При неизвестном моменте остаётся текст без выдуманного часа. Клиент поручений
  передаёт абсолютную дату с offset; правила интерпретации закреплены в
  [skill](../plugins/kitlane/skills/kitlane-work/SKILL.md).

Контракт ошибок в [connector_mcp.py](../services/connector_mcp.py):

| Результат | Действие клиента |
| --- | --- |
| `invalid_input`, 400 | Исправить поля/дату; не выдавать ошибку за сохранение |
| Отсутствие доступа / записи, 403 / 404 | Не подбирать чужие ID; попросить доступ или уточнение |
| `version_conflict`, 409 | Прочитать свежую запись и согласовать изменение |
| `idempotency_conflict`, 409 | Не обходить конфликт заменой ключа у прежней попытки |
| `retryable`, 503; неопределённый результат после timeout/500 | Повторить тот же ключ и payload; использовать возвращённые ID |
| OAuth / `invalid_token`, 401 | Подключиться заново; challenge содержит resource metadata |

Ошибка инструмента возвращается как MCP `isError` со structured error; HTTP
challenge используется на транспортном уровне. Не считать любой HTTP 200
транспорта подтверждением успешной бизнес-команды.

## Замечания и решение по ним

| Подтверждение / точная область | Влияние | Минимальное решение и категория |
| --- | --- | --- |
| Чтение через старый Manager order-detail могло запускать repair предложений; см. чистую [ConnectorQueryService](../services/connector_query_service.py) и [regression](../tests/integration/test_connector_mcp_queries.py) | Read-only MCP не должен изменять заказ | Исправлено в [#1089](https://github.com/mvnby/air-api/pull/1089) отдельной read-проекцией. Блокировало этот read-путь MVP; остальные Manager-пути не объявлены поломанными |
| Новый внешний actor нельзя получать из bot secret или tool arguments; см. CommandActor, ConnectorAuthService и [live auth tests](../tests/integration/test_connector_auth.py) | Иначе внешняя команда наследует неверную область доверия | Реализовано в #1089: персональный OAuth, scopes, live проверки ID/прав. Блокировало внешние write MVP |
| Для новых incoming/TODO нужны fingerprint, версии, durable receipt и attribution; см. общие command services и [MCP persistence test](../tests/integration/test_connector_mcp_persistence.py) | Retry/устаревшая правка могут создать дубль или стереть данные | Реализовано в #1089 с negative/concurrency checks. Блокировало эти write MVP; не вывод о каждом legacy endpoint |
| Chromium блокировал consent POST → 303 на ChatGPT из-за `form-action 'self'`; общая consent cookie связывала открытые формы. [Тесты](../tests/integration/test_connector_consent_browser.py), [CSP tests](../tests/unit/test_connector_consent_headers.py) | Первое подключение прерывалось, повтор использованной формы давал CSRF mismatch | Исправлено в [#1091](https://github.com/mvnby/air-api/pull/1091): точный callback CSP и существующий per-form server nonce без общей cookie. Блокировало подключение MVP |
| Быстрое обращение не предлагает готовое связанное поручение уточнения; [LeadInboxCard](../manager_frontend/src/components/leads/LeadInboxCard.vue) ведёт к общему списку. [LeadService.qualify](../services/lead_service.py) создаёт NEGOTIATION order, но не переносит intake-пожелание как отдельное поле заказа | Полный сценарий #1084 ещё не принят | Добавить связанное уточнение и явно проверить перенос договорённостей при квалификации; остаётся в [#1084](https://github.com/mvnby/air-api/issues/1084). Не блокирует простое сохранение входящего |
| [Быстрая форма](../manager_frontend/src/components/leads/QuickIncomingCapture.vue) позволяет ручные поля; automatic editable preview региона/услуги не реализован в IncomingCommandService | Полный быстрый разбор требует ещё одного среза | Расширить проверяемые предложения полей, сохраняя исходник; #1084. Не объявлять отсутствие нового preview багом старого API |
| Реальный ChatGPT callback/Android/голос/фото после deploy не подтверждены тестами браузера и сервера | Нельзя объявить весь personal plugin и мобильный пилот принятыми | Пройти ручные сценарии ниже; [#1087](https://github.com/mvnby/air-api/issues/1087), нужно до завершения пилота/партнёрского запуска |

Подтверждённые блокеры первого backend-среза устранены отдельными PR #1089 и
#1091; восстановление безопасного deployment —
[#1090](https://github.com/mvnby/air-api/pull/1090).
Переустройство всего API, всех bot-команд или всех больших файлов из этого
аудита не следует. Семантику legacy retry/voice parse следует отдельно проверять
только перед выставлением соответствующих операций наружу; их новая готовность
в этом отчёте не утверждается.

## Отсутствующие новые контракты

Наличие внутренних сервисов не означает наличие безопасного внешнего инструмента.
Для первого выпуска следующие операции не выставлены в MCP:

| Операция | Существующая основа | Что нужно перед внешним включением |
| --- | --- | --- |
| История оборудования | [EquipmentHistoryService](../services/equipment_history_service.py) | Отдельная scoped read-проекция, проверка equipment ID и consumer test; продолжение #1087 |
| Замечание после ТО / дефектный акт / согласованные допработы | [BotDefectActService](../services/bot_defect_act_service.py) | Shared actor-scoped команды жизненного цикла, версии и повторы; [#1085](https://github.com/mvnby/air-api/issues/1085) |
| Частные фото и вложения | [Manager attachments](../routers/manager_service_attachments.py) | Доступ к исходному объекту, безопасная выдача конкретного вложения и реальная проверка клиентского отображения; #1087 / #1085 |
| Расчёт предложения | [OrderProposalCommandService](../services/order_proposal_command_service.py) | Явный external command contract с actor, правами, retries/version и границей подтверждения; #1085 / #1087 |
| Черновик / выпуск документа | [DocumentService.generate_manager_order_document](../services/document_service.py) | Отделить read/preview от внешней мутации/выпуска, проверить права и повторы; #1085 / #1087 |
| Записи звонков из Drive | В первом MCP нет ingestion-инструмента | Durable source-event pipeline, права на источник, dedup и обработка отказов; [#1086](https://github.com/mvnby/air-api/issues/1086) |

Это новые контракты следующих этапов, а не доказанные поломки существующего API.
Для партнёрского/многопользовательского запуска нужны отдельная проверка реальных
учётных записей и регистраций, выбранных поверхностей и разрешённых сценариев.
Первый личный выпуск не означает публичную публикацию плагина в каталоге.

## Реально выполненная проверка выпуска

Результаты ниже относятся к выпущенному коду и указанным PR/run. Во время
подготовки этого Markdown тесты приложения повторно не запускались.

- [#1089](https://github.com/mvnby/air-api/pull/1089): 84 focused backend tests,
  97 существующих CRM/lifecycle regressions, полный operation-ID contract;
  upgrade всей Alembic history на пустой PostgreSQL, `alembic check` и focused
  downgrade/upgrade с сохранностью существующего Lead; синхронизированы
  OpenAPI/Manager client, component/UI logic checks и production build.
- Полный CI первого PR: 4417 unit, 729 integration и 4 worker-isolation proof.
- [#1091](https://github.com/mvnby/air-api/pull/1091): 81 focused backend tests;
  original code воспроизводимо проваливал callback/concurrent-form regressions;
  реальный Chromium на двух loopback origins подтвердил блокировку старой CSP,
  переход к разрешённому callback после исправления и запрет другого origin.
- [CI текущего release commit](https://github.com/mvnby/air-api/actions/runs/37496199913)
  успешен: Manager, build, backend contracts, unit и integration; это не только
  узкие новые тесты. Гейты проекта сохранены.

| Контроль | Проверка |
| --- | --- |
| Tenant/actor isolation, foreign links | [incoming tests](../tests/integration/test_incoming_commands.py), [task tests](../tests/integration/test_personal_tasks_service.py), [read tests](../tests/integration/test_connector_mcp_queries.py) |
| Отзыв / понижение прав / смена membership/credentials | [OAuth tests](../tests/integration/test_connector_auth.py), actual OAuth → MCP → PostgreSQL в persistence test |
| Same-key replay, changed payload, versions, audit | incoming/task/persistence tests; audit count не растёт при replay |
| Конкурентные physical connections | Один Lead при source-event retry; single-use code и refresh rotation в OAuth tests |
| Напоминание Manager | Task test: due → перенос → suppression после completion → replay/reopen; UI выводит banner/card. Отдельного UI assertion именно для banner и cancel-reminder assertion нет |
| Ошибки / transport / callback | [transport tests](../tests/unit/test_connector_mcp_transport.py), full-app consent tests и callback-header tests |

Полный UI тест не заменяет реальный телефонный пилот. Одновременная потеря
всех HA-узлов, disaster restore пользовательской записи и все legacy consumer
пути отдельно не проверялись и не входят в утверждение готовности этого среза.

## Production-снимок и эксплуатация

[Выпуск 37505852679](https://github.com/mvnby/air-api/actions/runs/37505852679)
успешен для commit `717f0d9fce0041c4ef4a030ca1a5b4eac281d63f`.
После выпуска оба активных API-контейнера независимо проверены на образ:

`ghcr.io/mvnby/air-api/backend@sha256:fb171f97f90a893b328e53db3d019400771ec0822a7a831f1fdb48f1bab4c95a`

Primary: health/readiness 200, scheduler работает. Replica: health 200,
readiness 503, traffic/scheduler отключены согласно HA-контракту.
16 публичных smoke checks прошли: обязательные health/products/filters,
readiness, Manager page/asset, OAuth discovery, MCP 401/challenge,
защищённые Manager routes и OAuth login guidance. На shared host восстановлены
Belzakupki worker/scheduler. Это датированный снимок, топологию перед новой
операцией проверять заново по [HA runbook](api-ha-runbook.md).

MCP можно приостановить `CONNECTOR_ENABLED=false` с перезапуском API; отзыв
подключений в Manager остаётся доступен. При откате образа сохранить additive
схему. Production downgrade удаляет новые пользовательские данные и не является
обычным откатом. Миграция `f10a2b3c4d5e` не требует backfill/provisioning/grants.

## Статус задач и следующий шаг

| Issue | Решение по объёму |
| --- | --- |
| [#1082](https://github.com/mvnby/air-api/issues/1082) | Ограниченный аудит завершён: операции/пути, access/retry/error/audit checks, findings, недостающие новые контракты и ссылки зафиксированы здесь |
| [#1083](https://github.com/mvnby/air-api/issues/1083) | MVP самостоятельных поручений реализован; выбранное напоминание внутри Manager видно при загрузке/обновлении списка, внешняя доставка — другой этап |
| [#1084](https://github.com/mvnby/air-api/issues/1084) | Закрыта после выпуска приёма/исправления, linked clarification, preview и переноса договорённостей при квалификации |
| [#1085](https://github.com/mvnby/air-api/issues/1085) | Закрыта: домен замечание → акт → предложение → согласование/выполнение выпущен; ограниченные MCP-адаптеры — срез #1087 |
| [#1086](https://github.com/mvnby/air-api/issues/1086) | Открыта: отдельный конвейер Drive, не блокирует текстовый ввод |
| [#1087](https://github.com/mvnby/air-api/issues/1087) | Первый MCP-срез выпущен; оставить открытой до клиентского пилота и остального заявленного объёма |

Следующему исполнителю сначала пройти свежий OAuth из ChatGPT: использованную
consent-форму после ошибки не отправлять повторно. Проверить в реальном аккаунте
поиск с неоднозначным совпадением, сохранение неполного обращения и исходного
текста в Manager, TODO без даты, versioned edit/complete/reopen, повтор write с
тем же ключом, отказ tool call после отзыва. Отдельно записать результаты Android,
голоса и фото, не выводить их из backend CI. Затем продолжить #1084, после него
#1085; Drive вести отдельной следующей очередью #1086.
