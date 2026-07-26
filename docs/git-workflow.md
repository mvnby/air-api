# Git Workflow (Safe Default)

Этот процесс нужен, чтобы не пушить рабочие изменения напрямую в `main`.

## Цели

- Снизить риск поломок в проде.
- Держать историю изменений понятной.
- Упростить ревью и откат.

## Правила веток

- `main`: только стабильный код, только merge через PR.
- `feat/*`: новая функциональность.
- `fix/*`: исправления багов.
- `refactor/*`: рефакторинг без изменения поведения.
- `hotfix/*`: срочные прод-фиксы.

Примеры:

- `feat/manager-leads-filters`
- `fix/install-toggle-fallback`
- `refactor/product-mapper-split`

## Ежедневный цикл работы

1. Обновить `main`:

   ```bash
   git checkout main
   git pull origin main
   ```

2. Создать ветку под задачу:

   ```bash
   git checkout -b fix/short-task-name
   ```

   Один раз настройте локальные git hooks (автосинк OpenAPI + manager client перед commit, если менялись роуты/схемы):

   ```bash
   ./scripts/setup_git_hooks.sh
   ```

3. Сделать изменения и локальную проверку:

   ```bash
   # Если менялись API схемы или роуты:
   ./scripts/sync_manager_api_client.sh
   
   pytest -q
   cd manager_frontend && npm run build
   ```

   Проверки storefront запускаются в отдельном `mvnby/mvn-web` PR. Запускайте
   только релевантные проверки, но перед merge в `main` CI должен быть зеленым.
4. Закоммитить:

   ```bash
   git add .
   git commit -m "Fix: short clear message"
   ```

5. Запушить ветку:

   ```bash
   git push -u origin fix/short-task-name
   ```

6. Открыть PR в `main`.
7. После green CI сделать `Squash and merge`.

## Правила PR

- Один PR = одна логическая задача.
- В описании PR:
  - что изменено;
  - как проверено;
  - риски/миграции/ручные шаги.
- Не merge, пока CI красный.

## Горячий фикс (prod)

1. Создать ветку от актуального `main`:

   ```bash
   git checkout main && git pull origin main
   git checkout -b hotfix/short-name
   ```

2. Минимальный фикс + быстрая проверка.
3. PR в `main` с пометкой `hotfix`.
4. После merge проверить deploy и smoke-check.

## Что не делать

- Не пушить рабочие изменения напрямую в `main`.
- Не смешивать refactor и feature в одном PR.
- Не оставлять незавершенные миграции в PR без инструкции деплоя.

## Чеклист перед merge

- CI зеленый.
- Миграции и post-deploy шаги описаны.
- Нет случайных изменений в несвязанных файлах.
- Есть план отката для рискованных изменений.
