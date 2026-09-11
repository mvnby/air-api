# Air API / Мастер Воздуха

Внутренняя платформа для витрины, CRM и операционных процессов проекта «Мастер Воздуха».

## Что входит в проект

- Backend API: FastAPI + SQLModel
- HTTP API для отдельной витрины `mvnby/mvn-web` (Astro + Vue)
- Manager CRM: Vue + FastAPI
- Manager admin: Vue + FastAPI (`manager_frontend/`)
- Внутренний API для Telegram-бота (`mvnby/mvn-telegram-bot`)
- Импортеры и парсеры товаров
- Генерация документов, договоров, актов и счетов
- Инструменты нормализации характеристик и продовых data-ops

## Основные возможности

- Каталог кондиционеров с SEO-ориентированной витриной
- Рекомендованная сортировка товаров по наличию, площади и приоритетам брендов
- CRM-заказы B2B/B2C с Kanban/List режимами
- Лиды, клиенты, заказы и квалификация обращений
- Управление товарами, характеристиками, фото и брендами
- Тарифы услуг и быстрые подсказки при составлении заказа
- Генерация документов с ролями сторон и шаблонами
- Google OAuth / Drive / Docs интеграции
- Импорт товаров от доноров и нормализация спецификаций

## Архитектура

### Backend

FastAPI-приложение с разделением слоев:

- `routers/` — API endpoints
- `services/` — бизнес-логика
- `crud/` — работа с БД
- `models/` — SQLModel-модели
- `schemas.py` — API-схемы
- `alembic/` — миграции

### Storefront

Публичная витрина на Astro + Vue живёт в отдельном репозитории
[`mvnby/mvn-web`](https://github.com/mvnby/mvn-web) и получает данные через HTTP API:

- SEO-страницы каталога
- карточки товаров
- фильтры
- страницы услуг/контента
- legal pages для OAuth verification

### Manager CRM

Современная админ-панель в `manager_frontend/`.

Все внутренние бизнес-функции должны разрабатываться в Manager UI.

### Legacy Admin

Legacy SQLAdmin удален. Старый `/admin` редиректит в менеджер, новые workflows добавляются только в Manager UI.

## Быстрый старт

```bash
docker compose up -d
```

Локальный API: [http://localhost:8000/docs](http://localhost:8000/docs).
Команды разработки и проверки: [docs/development-workflow.md](docs/development-workflow.md).

## Документация

Начните с [указателя по задачам](docs/README.md). Правила для агентов находятся в
[AGENTS.md](AGENTS.md); подробные процедуры читаются только по теме изменения.
