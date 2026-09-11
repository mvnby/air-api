# Документация MVN

Выберите строку под текущую задачу и читайте только связанные разделы.
Этот указатель не требует загрузки всей документации. Обязательные общие
ограничения находятся в [AGENTS.md](../AGENTS.md).

## Разработка и продуктовые контракты

| Задача | Точка входа |
| --- | --- |
| Локальный запуск, тесты, импорт, нормализация, лиды, генерация API-клиента | [Рабочие процедуры разработки](development-workflow.md) |
| Ветки, коммит, PR, проверка CI, merge | [Git-процесс](git-workflow.md) |
| Правила Manager, источники CRM-данных, доменные роутеры | [Процессы и поддержка](process.md) |
| Подбор оборудования, рабочая область каталога | [Решение по каталогу](adr/catalog-decision-workspace.md) |
| Библиотека характеристик | [Таксономия](catalog/feature-taxonomy-guide.md), [универсальные характеристики](catalog/universal-feature-library-v1.md) |
| Парсеры и импорт | [Добавление парсера](adding-parser.md), разделы импорта/нормализации в [рабочих процедурах](development-workflow.md) |
| Товарные подборки, инвалидация кэша | [Подборки](product-collections.md), [ревизии каталога](catalog-cache-invalidation.md) |
| Гарантия оборудования и её публичное представление | [Политики гарантии](warranty-policies.md), [публичный контракт](public-product-warranty.md) |
| Оборудование и обслуживание | [Обслуживание](equipment-maintenance.md), [продажа с монтажом в два этапа](b2c-two-stage-installation.md) |
| Карточка заказа и автосохранение | [Рабочая область заказа](order-workspace-usability.md), [автосохранение](manager-order-autosave.md), [декомпозиция](order-domain-refactor.md) |
| Генерация документов и шаблоны | [Архитектура](document-module-architecture.md), [DOCX-шаблоны](native-document-template-bundles.md), [плейсхолдеры](document-placeholders.md) |
| Ремонт и акты дефекта | [Сценарии ремонта](repair-workflow-v1.md), [акт дефекта V3](bot-defect-act-v3.md) |
| Медиа и приватные вложения | [R2/S3](media-storage-r2.md), [вложения сервиса](service-attachments.md) |
| Telegram и граница API | [Граница бота](bot-service-boundary.md), [выделение сервиса](bot-service-extraction.md) |
| Публичная витрина | [Граница отдельного репозитория](web-service-extraction.md); UI, сборка и деплой — в `mvnby/mvn-web` |
| Контекст витрины, tenant и цены | [Подписанный контекст](storefront-context-contract.md), [tenant scope](tenant-scope-rollout.md), [предложения](tenant-offer-contract.md), [селектор Manager](manager-storefront-selector-contract.md) |
| Подключение витрины и общий каталог | [Onboarding](storefront-onboarding.md), [системные grants](shared-catalog-grant.md) |
| Фид Яндекс Бизнеса | [Контракт и проверка фида](yandex-business-feed.md) |

## Эксплуатация

До операций с продовыми данными прочитайте [ограничения и команды](production-data-operations.md),
затем процедуру нужной операции. Наличие примера команды не разрешает её выполнение.
Сверяйте текущий релиз, топологию и свежий план; старый отчёт не заменяет эти проверки.

| Задача | Процедура |
| --- | --- |
| Релиз API, HA, Patroni, PITR | [Деплой](deployment.md), [HA](api-ha-runbook.md), [quorum](postgres-quorum-runbook.md) |
| Мониторинг и инфраструктурная безопасность | [VPS monitoring](api-vps-monitoring.md), [security](infrastructure-security-runbook.md) |
| Выдача доступа tenant-менеджеру | [Provisioning](tenant-manager-provisioning.md) |
| Исправление URL медиа | [Аудит и reviewed execute](product-media-url-backfill.md) |
| OAuth и ключи интеграций | [Google OAuth](google-oauth-token-runbook.md), [ключи интеграций](integration-credential-keyring-runbook.md), [подпись витрины](storefront-signing-keyring-runbook.md) |
| Communications rollout | [Профили и canary](communications-installation-estimate-rollout.md), [Telegram canary](communications-telegram-canary.md) |
| Orsha canary / legacy-owner cutover | [Orsha](orsha-storefront-canary.md), [legacy owner](legacy-owner-cutover.md); применять только к соответствующему сценарию |

## Планы, исследования и история

Эти документы читаются при работе над соответствующим решением, а не при каждой
правке. План может содержать как завершённые, так и будущие этапы; факт выпуска
проверяется по текущему коду и релизу.

- [Разделение сервисов](service-decomposition-roadmap.md) и
  [white-label platform](white-label-platform-plan.md) — архитектурное направление.
- [API reliability](api-reliability-plan.md) и
  [single-VPS migration](api-vps-migration-runbook.md) — контекст вариантов и
  конкретной миграции; для текущей HA-топологии начинать с HA/quorum runbooks выше.
- [Глобальный аудит от 12 июля 2026](global-system-audit-2026-07-12.md) — снимок на
  указанную дату, а не список гарантированно актуальных дефектов.
- [Аудит данных оборудования](catalog-decision-equipment-data-audit.md) — выводы
  по описанным выборкам и датам; перед исправлением данных повторить проверку.
- [Визуальная библиотека услуг](service-card-visual-library.md) — материалы для
  соответствующей задачи по контенту.
