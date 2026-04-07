# Добавление нового источника-парсера

Пошаговая инструкция по интеграции нового донора (источника товаров) в систему универсального импорта.

## Архитектура

```
parsers/
├── base.py            # BaseParser — абстрактный интерфейс
├── onliner.py         # OnlinerParser (catalog.onliner.by)
├── aircond.py         # AircondParser (aircond.by)
└── tvoy_klimat.py     # TvoyKlimatParser (tvoy-klimat.by)

services/
├── importer_service.py    # Оркестрация: роутинг по URL → парсер → сохранение
├── spec_normalizer.py     # KEY_MAP + clean_value + _split_dimensions
└── tag_logic.py           # Определение бренда, категории, автотегов
```

**Поток данных:**
1. Пользователь вставляет URL(ы) в модалку импорта
2. `ImporterService.find_parser(url)` выбирает парсер по домену
3. Парсер возвращает `dict` с `title`, `slug`, `price`, `specs`, `images`, `related_urls`
4. `ImporterService` сохраняет `Product`, прогоняет спеки через `normalize_specs()`
5. Если парсер вернул `save_gallery=True` — картинки скачиваются и сохраняются как `ProductImage`

---

## Пошаговый чеклист

### 1. Исследование HTML-структуры сайта

Используй браузер для анализа целевой страницы товара. Зафиксируй:

| Элемент | Что искать | Пример селектора |
|---------|------------|------------------|
| Название | `<h1>` | `h1.product__name`, `h1.switcher-title` |
| Цена | `meta[itemprop="price"]` или видимый элемент | `.price__new-val`, `span[property="price"]` |
| Спеки | Таблица или список ключ-значение | `.properties-group__item`, `table tr > th + td` |
| Картинки | Полноразмерные ссылки (не миниатюры!) | `a.detail-gallery-big__link[href]`, `img[src*="/media/"]` |
| Связанные товары | Ссылки на аналоги/серии | `a.series-products__link`, `.catalog-section-list a` |
| Описание | Текстовый блок | `.detail_text`, `.product__descr` |

> **Важно:** Предпочитай `meta[itemprop="price"][content]` вместо парсинга видимого текста цены — в тексте часто неразрывные пробелы (`\xa0`), валютные символы и т.п.

### 2. Создание парсера

Создай файл `parsers/<source_name>.py`:

```python
from parsers.base import BaseParser

class NewSourceParser(BaseParser):
    BASE_URL = "https://example.by"
    _HEADERS = {"User-Agent": "Mozilla/5.0 ..."}

    def supports(self, url: str) -> bool:
        return "example.by" in url

    async def parse(self, url: str) -> Dict[str, Any]:
        # ... fetch + BeautifulSoup ...
        return {
            "title": str,
            "slug": str,          # из последнего сегмента URL
            "description": str,
            "price": int,         # в BYN, целочисленный
            "area": int,          # площадь обслуживания м²
            "main_image": str,    # URL главной картинки
            "images": List[str],  # URL остальных картинок галереи
            "save_gallery": True, # True = ImporterService скачает и сохранит картинки
            "categories": [],     #
            "specs": dict,        # RAW спеки {русский_ключ: значение}
            "metrics": dict,      # Извлечённые метрики (area, is_inverter, power_cooling, ...)
            "related_urls": List[str],  # URL связанных товаров
        }
```

### 3. Регистрация в ImporterService

В `services/importer_service.py`:

```python
from parsers.new_source import NewSourceParser

class ImporterService:
    def __init__(self, ...):
        self.parsers: List[BaseParser] = [
            AircondParser(),
            TvoyKlimatParser(),
            NewSourceParser(),   # ← добавить
            OnlinerParser(),     # OnlinerParser всегда последний (наименее специфичный)
        ]
```

> **Порядок важен:** парсеры проверяются по `supports(url)` сверху вниз. OnlinerParser должен быть последним, т.к. его `supports()` может быть менее строгим.

### 4. Обновить placeholder в модалке импорта

В `manager_frontend/src/components/OnlinerImportModal.vue` — добавить пример URL нового источника в `placeholder` текстового поля.

---

## ⚠️ Критические нюансы (из реального опыта)

### Нюанс 1: Определение бренда из заголовка

**Проблема:** Функция `_extract_brand_from_title()` в `services/tag_logic.py` берёт **первое слово** заголовка, которое не в `_TITLE_SKIP_TOKENS`. Если заголовок начинается с типа продукта, он ошибочно станет брендом.

| Заголовок | Ожидание | Без фикса |
|-----------|----------|-----------|
| "Кассетный кондиционер TCL TCA-48CHRH" | TCL | ~~Кассетный~~ |
| "Канальный кондиционер Daikin FBA..." | Daikin | ~~Канальный~~ |

**Решение:** Слова-дескрипторы типа продукта должны быть в `_TITLE_SKIP_TOKENS` и `_INVALID_BRAND_EXACT`:

```
кассетный/ая, канальный/ая, потолочный/ая, подпотолочный/ая,
напольный/ая, напольно-потолочный/ая, колонный/ая, мобильный/ая,
оконный/ая, промышленный/ая, моноблок, моноблочный/ая
```

**Действие при добавлении нового парсера:** Проверь заголовки товаров — если начинаются с нового типа (например "Чиллер", "Фанкойл"), **обязательно добавь в оба списка.**

### Нюанс 2: Нормализация спеков (KEY_MAP)

**Проблема:** Каждый сайт использует свои формулировки ключей характеристик. Если ключ не найден в `KEY_MAP`, спека остаётся ненормализованной.

| Сайт | Ключ на сайте | Ожидаемый sys_key |
|------|--------------|-------------------|
| onliner | `Мощность охлаждения` | `capacity_cooling_kw` |
| tvoy-klimat | `Мощность в режиме охлаждения, кВт` | `capacity_cooling_kw` |
| aircond | `Мощность охлаждения` | `capacity_cooling_kw` |

**Решение:** После первого тестового импорта — проверь спеки импортированного товара. Все русские ключи, которые не нормализовались, нужно добавить в `KEY_MAP` в `services/spec_normalizer.py`.

**Типичные варианты, которые нужно покрыть:**
- С единицами измерения: `"Шум ..., дБ"`, `"Вес ..., кг"`, `"Площадь ..., м2"`
- С предлогами: `"Мощность в режиме охлаждения"` vs `"Мощность охлаждения"`
- Синонимы: `"наружный"` vs `"внешний"` блок
- Энергоклассы: `"Энергоэффективность при охлаждении"` (без `(EER)`) → `energy_class_cooling`

### Нюанс 3: Композитные габариты (ШхВхГ)

**Проблема:** Некоторые сайты дают габариты одной строкой `"940×1250×340"` вместо отдельных полей.

**Решение:** Добавь варианты ключа в `_DIMENSIONS_MAP` в `spec_normalizer.py`:

```python
_DIMENSIONS_MAP = {
    "Габариты внутреннего блока (ШхВхГ), мм": ("width_indoor", "height_indoor", "depth_indoor"),
    "Габариты внешнего блока (ШхВхГ), мм": ("width_outdoor", "height_outdoor", "depth_outdoor"),
    # ← добавь новые варианты здесь
}
```

Функция `_split_dimensions()` автоматически обработает разделители: `×`, `x`, `X`, `*`, `х` (кириллица).

### Нюанс 4: Картинки

- **Предпочитай полноразмерные картинки** (ссылки из `<a>`, а не `<img src="thumb...">`)
- Если сайт хостит картинки относительными путями — обязательно делай `urljoin` с `BASE_URL`
- Проверь формат: `.webp`, `.jpg`, `.png` — все поддерживаются, ImageService сохранит в том формате, в каком скачает
- `save_gallery=True` в ответе парсера сигнализирует `ImporterService` скачать и сохранить картинки как `ProductImage`

---

## Финальный чеклист перед PR

- [ ] Парсер создан и корректно извлекает: title, price, specs, images
- [ ] Парсер зарегистрирован в `ImporterService.parsers`
- [ ] Placeholder модалки обновлён
- [ ] Пробный импорт проведён, проверить:
  - [ ] Бренд определился корректно (не тип продукта)
  - [ ] Спеки нормализовались (нет raw русских ключей, которые имеют системные аналоги)
  - [ ] Габариты ШхВхГ разбились на width/height/depth (если применимо)
  - [ ] Картинки скачались и привязались к товару
- [ ] Новые ключи добавлены в `KEY_MAP` (spec_normalizer.py)
- [ ] Новые типы продуктов добавлены в `_TITLE_SKIP_TOKENS` (tag_logic.py)
- [ ] `npm run build` в `manager_frontend/` проходит без ошибок
- [ ] OpenAPI-клиент перегенерирован если менялись роутеры/схемы

---

## Справочник: существующие парсеры

| Парсер | Домен | Картинки | Спеки | Связанные товары |
|--------|-------|----------|-------|-----------------|
| `OnlinerParser` | `catalog.onliner.by` | Не сохраняет галерею | `table tr > th + td` | Нет |
| `AircondParser` | `aircond.by` | webp из `/media/` | `.product__specs table` | `.series-products__link` |
| `TvoyKlimatParser` | `tvoy-klimat.by` | jpg из `/upload/iblock/` | `.properties-group__item` | `.image-list__link` |
