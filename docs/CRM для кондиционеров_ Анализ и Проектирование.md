# **Архитектурный проект и техническое задание: Модуль управления заказами (Deals) для HVAC-предприятия**

## **Введение**

В условиях растущей конкуренции на рынке климатического оборудования (HVAC — Heating, Ventilation, and Air Conditioning) эффективность внутренних бизнес-процессов становится ключевым фактором выживания и масштабирования малого бизнеса. Переход от ручного управления к централизованной CRM-системе представляет собой не просто техническую модернизацию, а фундаментальный сдвиг в операционной модели предприятия. Для компании, состоящей из собственника, менеджера по продажам и аутсорс-бригад, критически важно, чтобы внедряемое решение минимизировало административное трение, обеспечивало прозрачность финансовых потоков и автоматизировало рутинные операции, такие как генерация документов и расчет сдельной оплаты труда.  
Данный отчет представляет собой исчерпывающее архитектурное руководство по проектированию и реализации модуля «Сделки/Заказы» (Deals) на базе существующего стека Python (FastAPI, SQLAdmin, SQLAlchemy). Проект учитывает специфику перехода на PostgreSQL и ограничения, накладываемые использованием библиотеки SQLAdmin в качестве основного интерфейса. В отчете детально проработаны вопросы бизнес-логики воронки продаж, проектирования схемы данных с учетом требований бухгалтерского учета (паттерн «Снимок продукта»), а также предложены решения для кастомизации UI/UX, превращающие стандартную административную панель в полноценный рабочий инструмент.  
Особое внимание уделено интеграции лучших практик управления продажами в HVAC, включая работу с «зависшими» лидами, стратегию резервирования складских остатков и автоматизацию взаимодействия с монтажными бригадами.

## **1\. Стратегический анализ и проектирование бизнес-логики (Pipeline)**

Проектирование воронки продаж для климатического бизнеса требует баланса между линейностью розничной торговли и итеративностью проектных продаж. В отличие от продажи коробочного продукта, продажа кондиционера с установкой — это процесс, включающий техническую экспертизу, логистику и производство работ на объекте заказчика. Оптимальная воронка должна не только отражать статус сделки, но и служить триггером для определенных действий системы (отправка КП, резерв товара, наряд на работы).

### **1.1. Концептуальная модель воронки продаж HVAC**

Основываясь на лучших практиках управления продажами в сфере услуг , предлагается расширить ваше первоначальное видение («Интерес» \-\> «Консультация» \-\>...) до 7-ступенчатой модели. Это необходимо для более гранулярного контроля конверсии и четкого разделения зон ответственности между продажами (Sales) и исполнением (Operations).

#### **Таблица 1: Предлагаемые этапы воронки продаж (Pipeline Stages)**

| Этап (Stage) | Системный код (Slug) | Вероятность (Probability) | Описание и цель этапа | Необходимые действия системы |
| :---- | :---- | :---- | :---- | :---- |
| **1\. Новый Лид** | new\_lead | 10% | Входящий запрос (звонок, форма с сайта, мессенджер). Цель: Квалификация (Локация, Бюджет, ЛПР). | Создание карточки Сделки. Привязка к Клиенту. |
| **2\. Тех. Осмотр / Замер** | assessment | 30% | Ключевой этап конверсии в HVAC. Выезд на объект для оценки сложности монтажа. | Генерация события в календаре. Сбор метаданных объекта (площадь, тип стен). |
| **3\. Коммерческое Предложение** | proposal\_sent | 50% | Подбор оборудования (SKU), расчет сметы монтажа. Отправка PDF клиенту. | Генерация документа «КП». Предварительная проверка остатков (без резерва). |
| **4\. Переговоры** | negotiation | 60% | Работа с возражениями, согласование цены и даты. | Отслеживание времени на этапе. Алерты при простое \> 7 дней. |
| **5\. Сделка (Предоплата)** | won\_deposit | 80% | Получение аванса. Точка невозврата. | **Жесткий резерв товара.** Формирование «Заказа на монтаж». |
| **6\. Монтаж / Исполнение** | installation | 90% | Физическое выполнение работ бригадой. | Смена статуса монтажников. Генерация Акта выполненных работ. |
| **7\. Закрыто (Успех)** | completed | 100% | Подписание акта, получение доплаты, активация гарантии. | Финальная Invoice. Начисление ЗП монтажникам. Закрытие сделки. |

### **1.2. Анализ и обработка «Сложных» клиентов (Nurture Strategy)**

Ваш вопрос о том, как обрабатывать клиентов, которые «думают», затрагивает фундаментальную проблему управления пайплайном — «засорение воронки» (Pipeline Stalling). Исследования показывают, что наличие большого количества неактивных сделок в активных статусах демотивирует менеджеров и искажает прогноз выручки.  
**Рекомендованная стратегия «Парковки»:** Клиенты, которые не отказались, но и не двигаются вперед в течение 14 дней, не должны висеть в статусе «Переговоры». Для них вводится специальный системный статус или отдельный «бакет» (bucket):

* **Статус:** deferred (Отложено / Взращивание).  
* **Логика:** Сделки в этом статусе скрываются с основной Канбан-доски (чтобы не создавать визуальный шум), но доступны в списочном виде с фильтром «Требует внимания».  
* **Механизм Re-engagement:** Система должна требовать обязательное поле next\_followup\_date (дата следующего касания) при переводе сделки в статус deferred.  
  * *Сценарий:* Клиент говорит «подумаю до лета». Менеджер ставит статус deferred и дату касания 15 мая. 15 мая система присылает уведомление или автоматически возвращает сделку в статус «Новый Лид» / «Интерес».

**Разделение отказов:** Важно различать типы неудач для аналитики:

* closed\_lost (Отказ): Клиент купил у конкурента или отказался (указывать причину).  
* abandoned (Недозвон): Клиент перестал выходить на связь после N попыток.

### **1.3. Стратегия управления ресурсами (Inventory & Labor Allocation)**

Ответ на вопрос «На каком этапе резервировать товар и назначать монтажников?» определяет финансовую безопасность бизнеса.  
**Резервирование товара (Inventory Reservation):**

* **Рекомендация:** Строго на этапе **5\. Сделка (Предоплата)**.  
* **Обоснование:** Резервирование на этапе КП (proposal\_sent) замораживает оборотный капитал. Если клиент «думает» неделю, вы можете упустить реального покупателя, которому нужен этот кондиционер «здесь и сейчас». Однако, на этапе КП система должна показывать «Доступный остаток» (Soft Check), чтобы менеджер не продал то, чего нет. Жесткий резерв (Hard Reserve) в базе данных ставится только после поступления денег.

**Назначение монтажников (Crew Assignment):**

* **Предварительное (Soft Booking):** Может происходить на этапе **Переговоров**, если клиент требует конкретную дату («Хочу установку в субботу 15-го»). В календаре создается «черновая» запись.  
* **Фактическое (Hard Booking):** Происходит на этапе **5\. Сделка (Предоплата)**. В этот момент генерируется наряд-заказ (Work Order), и монтажники получают уведомление. До получения предоплаты график монтажников должен оставаться гибким для оплаченных заказов.

## **2\. Проектирование схемы данных (Technical Data Model)**

Для реализации описанной логики на стеке SQLAlchemy \+ PostgreSQL требуется нормализованная схема данных. Мы используем подход Code-First с использованием ORM. Ключевым архитектурным решением здесь является использование паттерна «Снимок продукта» (Product Snapshot) и «Ассоциативная сущность» для монтажников.

### **2.1. Концептуальная схема (ERD Analysis)**

Система строится вокруг центральной сущности Order (Сделка), которая агрегирует связи с клиентом, товарами, монтажниками и документами.

#### **Сущность: Order (Заказ/Сделка)**

Это корневой агрегат. Он хранит состояние процесса и финансовые итоги. Использование JSONB для метаданных (meta\_data) критически важно для HVAC, так как технические параметры (длина трассы, тип стен, наличие альпиниста) могут варьироваться от объекта к объекту и не всегда укладываются в жесткую схему.

#### **Сущность: OrderItem (Позиция заказа) — Паттерн Snapshot**

**Проблема:** Если вы просто свяжете Заказ с Продуктом (ForeignKey('product.id')), то при изменении цены кондиционера в справочнике (сезонное подорожание), старые (уже закрытые) заказы пересчитаются и покажут неверную сумму. **Решение:** Сущность OrderItem должна копировать цену и себестоимость товара **в момент добавления в заказ**. Это замораживает финансовую историю сделки.

#### **Сущность: OrderInstaller (Связь с монтажниками)**

Так как работа сдельная, нам недостаточно просто знать, *кто* делал монтаж. Нам нужно знать, *сколько* мы договорились заплатить за этот конкретный объект. Оплата может отличаться от стандартной ставки из\-за сложности (высотность, штробление). Поэтому используется связь Many-to-Many с дополнительными полями (Association Object).

### **2.2. Реализация моделей SQLAlchemy**

Ниже представлен код моделей, готовый к интеграции.  
`import enum`  
`from datetime import datetime`  
`from typing import List, Optional`  
`from sqlalchemy import (`  
    `Column, Integer, String, ForeignKey, DateTime,`   
    `Enum, Numeric, JSON, Boolean, Text, Table`  
`)`  
`from sqlalchemy.orm import relationship, Mapped, mapped_column, declarative_base`  
`from sqlalchemy.sql import func`

`Base = declarative_base()`

`# --- Enums ---`  
`class OrderStatus(str, enum.Enum):`  
    `NEW_LEAD = "new_lead"          # Новый лид`  
    `ASSESSMENT = "assessment"      # Замер/Осмотр`  
    `PROPOSAL = "proposal_sent"     # КП отправлено`  
    `NEGOTIATION = "negotiation"    # Переговоры`  
    `DEFERRED = "deferred"          # Отложено/Думают`  
    `WON_DEPOSIT = "won_deposit"    # Предоплата получена`  
    `INSTALLATION = "installation"  # Монтаж`  
    `COMPLETED = "completed"        # Закрыто`  
    `CANCELED = "canceled"          # Отмена`

`# --- Models ---`

`class Client(Base):`  
    `__tablename__ = 'clients'`  
    `id = Column(Integer, primary_key=True)`  
    `name = Column(String, nullable=False, index=True)`  
    `phone = Column(String, unique=True, index=True)`  
    `email = Column(String, nullable=True)`  
    `address = Column(String, nullable=True)`  
    `source = Column(String, nullable=True) # Откуда пришел (SEO, Referrals)`  
      
    `orders = relationship("Order", back_populates="client")`

`class Product(Base):`  
    `__tablename__ = 'products'`  
    `id = Column(Integer, primary_key=True)`  
    `sku = Column(String, unique=True)`  
    `name = Column(String)`  
    `current_price = Column(Numeric(10, 2)) # Цена продажи`  
    `current_cost = Column(Numeric(10, 2))  # Себестоимость`  
    `stock_quantity = Column(Integer, default=0)`

`class Order(Base):`  
    `__tablename__ = 'orders'`

    `id = Column(Integer, primary_key=True, index=True)`  
      
    `# 1. Связь с клиентом`  
    `client_id = Column(Integer, ForeignKey('clients.id'), nullable=False)`  
    `client = relationship("Client", back_populates="orders")`

    `# 2. Статус и Метаданные сделки`  
    `status = Column(Enum(OrderStatus), default=OrderStatus.NEW_LEAD, index=True)`  
    `title = Column(String(200), nullable=True) # Напр: "Монтаж Split-системы в гостиную"`  
      
    `# JSON для технических деталей (HVAC специфика)`  
    `# Пример: {"wall_type": "beton", "pipe_length": 5, "wifi_module": true}`  
    `technical_meta = Column(JSON, default={})` 

    `# 3. Финансы (Денормализация для скорости отчетов)`  
    `total_amount = Column(Numeric(10, 2), default=0.00) # Итого клиенту`  
    `total_cost = Column(Numeric(10, 2), default=0.00)   # Себестоимость (Товары + Монтаж)`  
    `margin = Column(Numeric(10, 2), default=0.00)       # Маржа`  
    `is_paid = Column(Boolean, default=False)            # Флаг полной оплаты`

    `# 4. Даты`  
    `created_at = Column(DateTime(timezone=True), server_default=func.now())`  
    `assessment_date = Column(DateTime, nullable=True)   # Дата замера`  
    `installation_date = Column(DateTime, nullable=True) # Дата монтажа`  
    `closed_at = Column(DateTime, nullable=True)`

    `# 5. Связи`  
    `items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")`  
    `installers = relationship("OrderInstaller", back_populates="order", cascade="all, delete-orphan")`

`class OrderItem(Base):`  
    `"""Связывает товар с заказом, фиксируя цену на момент сделки"""`  
    `__tablename__ = 'order_items'`  
      
    `id = Column(Integer, primary_key=True)`  
    `order_id = Column(Integer, ForeignKey('orders.id'), nullable=False)`  
    `product_id = Column(Integer, ForeignKey('products.id'), nullable=False)`  
      
    `quantity = Column(Integer, default=1)`  
      
    `# SNAPSHOT PRICES - Критически важно для истории`  
    `unit_price_at_sale = Column(Numeric(10, 2), nullable=False)`   
    `unit_cost_at_sale = Column(Numeric(10, 2), nullable=False)`  
      
    `order = relationship("Order", back_populates="items")`  
    `product = relationship("Product")`

`class Installer(Base):`  
    `__tablename__ = 'installers'`  
    `id = Column(Integer, primary_key=True)`  
    `name = Column(String)`  
    `is_active = Column(Boolean, default=True)`  
    `default_rate = Column(Numeric(10, 2)) # Базовая ставка`

`class OrderInstaller(Base):`  
    `"""Ассоциативная таблица для назначения бригады и фиксации оплаты"""`  
    `__tablename__ = 'order_installers'`  
      
    `order_id = Column(Integer, ForeignKey('orders.id'), primary_key=True)`  
    `installer_id = Column(Integer, ForeignKey('installers.id'), primary_key=True)`  
      
    `# Роль (Бригадир/Помощник)`  
    `role = Column(String(50), default="main")`   
      
    `# Сколько платим за ЭТОТ конкретный монтаж (Сдельная)`  
    `agreed_pay = Column(Numeric(10, 2), nullable=False)`  
      
    `# Статус выплаты монтажнику`  
    `is_paid_to_installer = Column(Boolean, default=False)`  
      
    `order = relationship("Order", back_populates="installers")`  
    `installer = relationship("Installer")`

### **2.3. Генерация документов на этапах**

Система должна автоматически предлагать сгенерировать документы при смене статуса. Технически это реализуется через кнопки действий (Custom Actions) в SQLAdmin, которые вызывают генератор PDF (например, WeasyPrint или ReportLab).

1. **Этап PROPOSAL \-\> Документ: Коммерческое предложение (Quote)**  
   * *Данные:* Инфо о клиенте, Список товаров (OrderItem), Цены, Итого, Срок действия, Условия.  
   * *Особенность:* Не показывать себестоимость и данные о монтажниках.  
2. **Этап INSTALLATION \-\> Документ: Наряд-заказ (Work Order)**  
   * *Данные:* Адрес клиента, Телефон, Список оборудования (БЕЗ ЦЕН), Технические метаданные (technical\_meta: "3 этаж, без лифта, ключ у консьержа").  
   * *Цель:* Выдается монтажнику.  
3. **Этап COMPLETED \-\> Документ: Счет-фактура / Акт (Invoice)**  
   * *Данные:* Финальные суммы, Гарантийные обязательства (серийные номера).

## **3\. UI/UX в рамках SQLAdmin: Кастомизация и Канбан**

SQLAdmin «из коробки» предоставляет отличный табличный интерфейс (Data Grid), но для управления потоком сделок необходима визуализация. Поскольку вы ограничены этой библиотекой, мы используем гибридный подход: стандартные CRUD-интерфейсы для редактирования данных и кастомную страницу (Custom View) для Канбан-доски.

### **3.1. Канбан-доска: Интеграция Custom View**

SQLAdmin позволяет добавлять произвольные страницы через BaseView и методы @expose. Мы создадим страницу, которая рендерит HTML-шаблон с колонками, соответствующими нашим статусам.  
**Техническое решение:**

1. **HTML/Jinja2:** Шаблон, наследуемый от базового лайаута SQLAdmin (чтобы сохранить меню и стили).  
2. **JS Library:** Использование SortableJS (или Htmx \+ Sortable) для реализации Drag-and-Drop без тяжелого фронтенд-фреймворка.  
3. **API Endpoint:** При перетаскивании карточки JS отправляет AJAX-запрос на FastAPI endpoint для обновления статуса в БД.

**Макет карточки сделки (в колонке):**

* **Заголовок:** Имя Клиента \+ Краткое название («Иванов \- Мультисплит»).  
* **Тело:**  
  * Сумма сделки (выделено жирным).  
  * Дата следующего действия (красным, если просрочено).  
  * Иконка монтажника (если назначен).  
* **Футер:** Кнопка быстрого перехода к редактированию (/admin/order/edit/{id}).

**Пример реализации View (Python):**  
`from sqladmin import BaseView, expose`  
`from models import Order, OrderStatus`

`class KanbanView(BaseView):`  
    `name = "Воронка продаж"`  
    `icon = "fa-solid fa-columns"`

    `@expose("/kanban", methods=)`  
    `async def kanban_page(self, request):`  
        `# Получаем все активные сделки (исключая архивированные)`  
        `# Группируем их по статусам для передачи в шаблон`  
        `async with self.session_maker() as session:`  
            `# (Логика запроса к БД через select(Order)...)`  
            `pass`   
          
        `return await self.templates.TemplateResponse(`  
            `request,`   
            `"kanban.html",`   
            `context={"orders_by_status": grouped_orders}`  
        `)`

### **3.2. Оптимизация Списочного Вида (List View)**

Для тех случаев, когда канбан неудобен (поиск, аналитика), табличный вид должен быть максимально информативным.  
**Рекомендуемая конфигурация ModelView:**  
`class OrderAdmin(ModelView, model=Order):`  
    `name = "Сделка"`  
    `name_plural = "Сделки"`  
    `icon = "fa-solid fa-briefcase"`

    `# Какие поля показывать в таблице`  
    `column_list =`

    `# Визуализация статусов (Цветные бейджи)`  
    `def status_formatter(view, context, model, name):`  
        `status = getattr(model, name)`  
        `colors = {`  
            `OrderStatus.WON_DEPOSIT: "green",`  
            `OrderStatus.NEW_LEAD: "blue",`  
            `OrderStatus.NEGOTIATION: "yellow",`  
            `OrderStatus.CANCELED: "red"`  
        `}`  
        `color = colors.get(status, "gray")`  
        `# SQLAdmin использует Bootstrap/Tabler классы`  
        `return Markup(f'<span class="badge bg-{color}-lt">{status.value}</span>')`

    `column_formatters = {`  
        `Order.status: status_formatter`  
    `}`

    `# Поиск и Фильтры`  
    `column_searchable_list = [Order.title, "client.name", "client.phone"]`  
    `column_filters = [Order.status, Order.created_at, Order.installation_date]`  
      
    `# Сортировка по умолчанию: Сначала новые и "горячие"`  
    `column_default_sort = ("created_at", True)`

### **3.3. Главная страница (Dashboard)**

Главная страница админки (/admin) должна давать мгновенное понимание ситуации («Health Check»). Используя кастомизацию шаблона index.html в SQLAdmin , рекомендую вывести следующие виджеты:

1. **Финансовый прогноз (Воронка):**  
   * Гистограмма: Сумма сделок по этапам. Позволяет понять, сколько денег «зависло» в переговорах.  
2. **Оперативный список (Action Items):**  
   * Таблица: «Монтажи на сегодня/завтра».  
   * Таблица: «Просроченные замеры» (дата замера \< сегодня и статус \= assessment).  
3. **Загрузка бригад:**  
   * Простой список монтажников с количеством активных назначенных заказов. Помогает избежать перегрузки одной бригады.  
4. **Счетчик «Зависших»:**  
   * Большая цифра красным цветом: Количество сделок в статусе deferred или negotiation без активности более 14 дней.

## **4\. Глубокий анализ специфики HVAC и рекомендации**

### **4.1. Специфика оплаты труда монтажников**

В малом бизнесе HVAC часто используется комбинированная система оплаты: фиксированная ставка за стандартный монтаж («сделка») \+ доплаты за сложность (высотные работы, штробление). Предложенная модель OrderInstaller с полем agreed\_pay позволяет реализовать гибкость.  
**Сценарий работы:**

1. Менеджер создает заказ. В OrderItems добавляется услуга «Стандартный монтаж 07-09 модели» (например, 5000 руб). Это цена *для клиента*.  
2. Менеджер назначает бригаду в OrderInstaller. Система может автоматически подтянуть default\_rate монтажника (например, 2500 руб) в поле agreed\_pay.  
3. Если объект сложный, менеджер вручную меняет agreed\_pay на 3000 руб, не меняя цену для клиента.  
4. **Результат:** Система автоматически считает маржинальность сделки (margin), вычитая из суммы заказа стоимость оборудования и индивидуальную стоимость работ.

### **4.2. Сезонность и управление складом**

В HVAC критична сезонность.

* **Рекомендация:** Внедрите в OrderAdmin предупреждение (Alert) на этапе PROPOSAL, если stock\_quantity товара меньше 3 единиц. Это спасет от ситуации, когда КП отправлено, клиент думал неделю, а кондиционеры закончились.  
* **Реализация:** Переопределение метода on\_model\_change или валидация формы в SQLAdmin для проверки остатков перед сменой статуса на WON\_DEPOSIT.

### **4.3. Технические метаданные (JSONB)**

Почему JSON, а не отдельные колонки? В HVAC параметры оборудования и объекта постоянно меняются. Сегодня вам нужно знать диаметр трубок, завтра — наличие Wi-Fi модуля, послезавтра — длину трассы. Использование поля technical\_meta (тип JSONB в PostgreSQL) позволяет добавлять любые параметры прямо в интерфейсе (если использовать редактор JSON в SQLAdmin) без миграций базы данных. Это дает огромную гибкость для малого бизнеса.

* *Пример данных:* {"trassa\_length": 5, "drenazh": "gravity", "power\_source": "outdoor"}.

## **5\. План реализации (Implementation Roadmap)**

1. **Фаза 1: База данных (Week 1\)**  
   * Настройка PostgreSQL.  
   * Реализация моделей SQLAlchemy (Order, OrderItem, OrderInstaller) с учетом всех External Keys и Constraints.  
   * Настройка Alembic для миграций.  
2. **Фаза 2: CRUD интерфейс (Week 2\)**  
   * Подключение SQLAdmin.  
   * Настройка OrderAdmin (списки, фильтры, форма редактирования с InlineModel для товаров).  
   * Реализация цветовой кодировки статусов.  
3. **Фаза 3: Канбан и Визуализация (Week 3\)**  
   * Создание KanbanView endpoint.  
   * Верстка шаблона kanban.html с использованием SortableJS.  
   * Написание JS-скрипта для обновления статусов через API.  
4. **Фаза 4: Документы и Логика (Week 4\)**  
   * Интеграция генератора PDF (WeasyPrint).  
   * Создание кнопок действий ("Скачать КП", "Скачать Наряд").  
   * Тестирование расчета маржи и начислений монтажникам.

## **Заключение**

Предложенная архитектура превращает вашу админку из простой базы данных в операционную систему бизнеса. Использование гибридного подхода в SQLAdmin (таблицы \+ кастомный Канбан) решает задачу визуализации без дорогостоящей разработки отдельного фронтенда. Модель данных с фиксацией цен (Snapshot) и гибкой оплатой труда обеспечивает точность финансового учета, критически важную для масштабирования малого бизнеса в сфере услуг. Следуя этому плану, вы получите инструмент, который не просто хранит данные, а помогает вести сделку от первого звонка до успешного монтажа.

#### **Источники**

1\. How to Build an Effective Commercial HVAC Sales Process \- ServiceTitan, https://www.servicetitan.com/blog/commercial-hvac-sales-process 2\. HVAC Sales Process: How to Improve Conversions \- Rocket Media, https://rocketmedia.com/resources/hvac-sales-process 3\. HVAC Sales Process & the Buyer's Journey \- Commusoft, https://www.commusoft.com/en-us/blog/hvac-sales-process/ 4\. 4 Tactics for Moving Stalled Deals Through the Pipeline \- The Brooks Group, https://brooksgroup.com/sales-training-blog/4-tactics-moving-stalled-deals-through-pipeline/ 5\. From Stagnant to Success: Un-stalling Deals in Your Pipeline \- Sales Gravy, https://salesgravy.com/from-stagnant-to-success-un-stalling-deals-in-your-pipeline/ 6\. Why Your Sales Pipeline Stalls and How to Fix It \- Athena SWC | Lead Generation for Manufacturing Companies, https://www.athenaswc.com/resources/blog/why-your-sales-pipeline-stalls-and-how-to-fix-it/ 7\. Database Design for Product Sales System \- Oreate AI Blog, https://www.oreateai.com/blog/database-design-for-product-sales-system/0f61353d00a3673c7659acdbd1758a50 8\. examples.association.basic\_association — SQLAlchemy 2.0 Documentation, http://docs.sqlalchemy.org/en/latest/\_modules/examples/association/basic\_association.html 9\. Basic Relationship Patterns — SQLAlchemy 2.0 Documentation, http://docs.sqlalchemy.org/en/latest/orm/basic\_relationships.html 10\. Basic Relationship Patterns — SQLAlchemy 1.4 Documentation, https://docs.sqlalchemy.org/14/orm/basic\_relationships.html 11\. Generate PDFs in Python & Django with WeasyPrint — Step by Step Guide | by Francisco, https://blog.franciscoarocas.com/generate-pdfs-in-python-django-with-weasyprint-step-by-step-guide-e26fbb0d3a72 12\. Top 10 Python PDF generator libraries: Complete guide for developers (2025) \- Nutrient iOS, https://www.nutrient.io/blog/top-10-ways-to-generate-pdfs-in-python/ 13\. sqladmin/sqladmin/application.py at main · aminalaee/sqladmin \- GitHub, https://github.com/aminalaee/sqladmin/blob/main/sqladmin/application.py 14\. How to make use of the database session in a custom view? · aminalaee sqladmin · Discussion \#406 \- GitHub, https://github.com/aminalaee/sqladmin/discussions/406 15\. Sortable \- \</\> htmx \~ Examples, https://htmx.org/examples/sortable/ 16\. SortableJS, https://sortablejs.github.io/Sortable/ 17\. Working with Templates \- SQLAlchemy Admin \- GitHub Pages, https://aminalaee.github.io/sqladmin/working\_with\_templates/ 18\. HVAC Commission Pay: How to Design a Plan That Drives Profit (Not Problems), https://www.sharewillow.com/blog/hvac-commission-pay 19\. HVAC Sales Commission Rates & Processes That Work \- ServiceTitan, https://www.servicetitan.com/blog/hvac-sales-commission