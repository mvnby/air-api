# Дизайн-система «МАСТЕР ВОЗДУХА» (UI Checklist)

Краткое руководство для сохранения преемственности стиля на всех страницах проекта.

## 🎨 Цветовая палитра и Темы (Light / Dark)
Мы используем адаптивную вёрстку через модификаторы Tailwind `dark:...` или CSS-переменные.
- **Основной цвет (Teal)**: `#007f80` — акценты, основные кнопки. Одинаково хорошо смотрится на светлом и темном.
- **Светлая тема (По умолчанию)**:
  - Background: `bg-slate-50` или `bg-white`
  - Карточки: `bg-white border-slate-200`
  - Текст: `text-slate-900` (основной), `text-slate-500` (второстепенный)
- **Тёмная тема (`dark:` модификаторы)**:
  - Background (Surface): `dark:bg-[#0f172a]` (Slate 900)
  - Карточки (Secondary Surface): `dark:bg-[#1e293b]` (Slate 800), `dark:border-slate-700/50`
  - Текст: `dark:text-white`, `dark:text-slate-400`
- **Градиент**: `linear-gradient(90deg, #007f80, #2dd4bf)` — для «хайлайтов» в заголовков.
- **Тёмная тема**:
  - Background (Surface): `#0f172a` (Slate 900)
  - Secondary Surface: `#1e293b` (Slate 800)
  - Text Muted: rgba(255, 255, 255, 0.6)

### Theme Token Contract (Обязательно)
Источник токенов: `web/src/assets/index.css`.

Для panel / glass / filter UI использовать только глобальные токены:
- `--panel-glass-bg`
- `--panel-glass-border`
- `--panel-glass-shadow`
- `--panel-chip-bg`
- `--panel-chip-border`
- `--panel-chip-hover-border`
- `--panel-pill-bg`
- `--panel-input-bg`
- `--panel-input-border`
- `--panel-active-gradient`
- `--panel-active-gradient-alt`
- `--panel-active-text`
- `--panel-skeleton`

Запрещено в component-level стилях (кроме `web/src/assets/index.css`):
- Хардкодить светлые panel-значения вида `rgba(255,255,255,...)`, `#fff`, `#ffffff`.
- Хардкодить градиенты активных tab/pill (`#0f8f8d -> #3aa56e`, `#0a8e8c -> #2b6eb3`) напрямую в компонентах.

Перед PR по UI запускать аудит:
- `bash scripts/audit_theme_hardcodes.sh`
- или из `web/`: `npm run audit:theme`

## ✍️ Типографика
- **Заголовки (Headings)**: `Space Grotesk` (700-800 weight). Характерный, технологичный вид.
- **Основной текст (Body)**: `Inter` (стандарт). Чистота и читаемость.
- **Межстрочка**: `line-height: 1.6` для комфортного чтения.

## 📱 Компоненты и Эффекты
- **Скругления (Border Radius)**: 
  - Большие карточки: `2rem` (32px)
  - Кнопки, инпуты, чипсы: `12px` или `1rem`
- **Glassmorphism**: Для шапки и floating-элементов: `backdrop-filter: blur(12px)` + прозрачность 0.8.
- **Интерактив**: Hover-анимации с `transform: translateY(-4px)` или `scale(1.02)`, мягкие тени (`box-shadow`).
- **Иконки**: Строго `Material Icons Round`.

## 📐 Сетка и Раскладка
- **Контейнер**: Max ширина `1200px` (padding 1.5rem по бокам).
- **Сетки товаров**: 3 колонки (Desktop) → 2 (Tablet) → 1 (Mobile).
- **Отступы**: Умеренные вертикальные отступы между секциями (`4rem - 6rem`) для баланса пространства.

## 🏷 Рекомендации по UX
- **Theme-Aware Branding**: Логотип меняется: Бирюзовый (Light) ↔ Белый (Dark).
- **Акценты**: Использовать Teal экономно, чтобы он «выскакивал» на фоне нейтральных поверхностей.
- **Микро-интерактивы**: Смена цены при включении опций (как с монтажом) — обязательный паттерн.

## 🔔 Обратная связь (Feedback)
- **Тосты (Toasts)**: Всплывающие уведомления (Top-Right) для подтверждения действий ("Товар добавлен").
- **Морфинг кнопок**: Кнопка действия меняет состояние (Icon: Cart -> Check, Color: Primary -> Success) на 2 секунды.
- **Ошибки**: Inline-валидация в формах (красный текст под полем).

## 🖼 Иллюстрации
- **Стиль**: "Modern Isometric" или минималистичный 3D.
- **Цвета**: Белый фон, Teal (#007f80) для основных объектов, светло-серый для теней.
- **Детали**: Чистые линии, отсутствие лишнего шума и текста. Технологичный, "инженерный" вид.

## Homepage conversion analytics

Главная страница использует существующий GTM `dataLayer` без дополнительного SDK.
Элементы размечаются атрибутами `data-home-event`, `data-home-action` и
`data-home-item`; поле `destination` берётся из реального `href`. PII в события
не передаётся.

События этапа 1:

- `home_hero_select_click` — переход из hero в каталог;
- `home_hero_installation_click` — переход к сценарию расчёта монтажа;
- `home_intent_click` — выбор одной из четырёх задач;
- `home_quick_pick_click` — переход в поддерживаемую виртуальную категорию;
- `home_product_fit_click` — проверка подходящей модели из блока наличия;
- `home_mobile_action_click` — `call`, `write` или `select` в мобильной панели.
