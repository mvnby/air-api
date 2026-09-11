# Аудит данных для подбора оборудования

Проверено: 2026-09-11 00:51 Europe/Minsk.

Это read-only срез опубликованного каталога. Запросы выполнялись к публичному
`https://api.mvn.by/api/v1/products`; Manager API и учётные данные
не использовались, записи каталога не изменялись.

## Обогрев по наружной температуре

Публичный каталог уже поддерживает параметр `heating_min` с семантикой
«заявленный минимум температуры не выше выбранного порога». На момент проверки
он вернул следующие totals:

| Порог | Опубликованных моделей |
| --- | ---: |
| -20 °C | 311 |
| -25 °C | 144 |
| -30 °C | 30 |

Числа вложены ожидаемым образом: выбор `-25 °C` должен включать модели `-30 °C`.
Canonical источник для нового Manager-фильтра — typed
`__typed_specs.temp_range_heat.min`; `__filter_min_heat` остаётся fallback для
исторических нормализованных записей. Отсутствующее либо некорректное значение
не должно быть совпадением.

## Консольные блоки: первоначальная выборка

Публичный текущий фильтр `indoor_types=floor_ceiling` вернул 69 моделей, а
`indoor_types=column` — 22. Среди первых обнаружены две явные console-кандидатуры;
среди вторых совпадений по названию, серии или типу не найдено.

| Public ID | Название | Серия | Canonical type | Текущий indoor type | Температура обогрева | Public source URL |
| ---: | --- | --- | --- | --- | --- | --- |
| 1021 | Внутренний напольно-потолочный блок MDV Консольные внутренние блоки MDFFI-12HRFN8 | Консольные внутренние блоки | внутренний блок | напольно-потолочный | — | — |
| 1022 | Внутренний напольно-потолочный блок MDV Консольные внутренние блоки MDFFI-18HRFN8 | Консольные внутренние блоки | внутренний блок | напольно-потолочный | — | — |

Поле `source_url` отсутствует и в публичном detail-ответе модели 1021, поэтому
публичный API сам по себе не предоставляет доказательство для мутации.
Независимая проверка первоисточника MDV подтверждает именно консольный тип для
[MDFFI-12HRFN8 и MDFFI-18HRFN8](https://mdv-aircond.ru/catalog/multisplit-sistemy/konsolnye-bloki_/konsolnye-vnutrennie-bloki-multisplit/),
а отдельная карточка [MDFFI-18HRFN8](https://mdv-aircond.ru/catalog/multisplit-sistemy/konsolnye-bloki_/konsolnye-vnutrennie-bloki-multisplit/konsolnye_vnutrennie_bloki_console_multi_mdffi-18hrfn8/)
называет его «Консольный внутренний блок».

## Уточнение по пяти сериям (2026-09-11, Europe/Minsk)

Первичная выборка выше была слишком узкой: она искала только уже сохранённые
`floor_ceiling` и `column`. Публичные записи TCL и Kinghome имеют сейчас
`indoor_type=настенный`, поэтому в неё не попали. Ниже приведены точные
результаты публичных карточек `api/v1/products` и проверка доступных
первоисточников. Значение «category» в таблице — slug тега из группы
`category`, а не вывод из названия.

| Series ID | Public ID и модели | Текущая category | Product kind / type / indoor type | Обогрев | Persisted API `series.source_url` | Первичный / исследовательский источник и форма |
| ---: | --- | --- | --- | --- | --- | --- |
| 276, TCL Console Inverter ZHRH | 1431 `TCC-09ZHRH/DV`; 1429 `TCC-12ZHRH/DV`; 1430 `TCC-18ZHRH/DV` | `cat-industrial` | `complete_split_system` / `сплит-система` / `настенный` | от -20 до +30 °C | [TCL Console](https://www.tcl.com/global/en/air-conditioners/console) | Консольная: европейская официальная [Console Z Series](https://www.tcl.com/eu/en/air-conditioners/console) относит серию к Console и Light Commercial. |
| 87, Kinghome Consol | 767 `KEH09AAXB-K6DNA1A`; 777 `KEH12AAXD-K6DNA1A`; 778 `KEH18AAXF-K6DNA1A` | `cat-household` | `complete_split_system` / `сплит-система` / `настенный` | от -22 до +24 °C | [Kinghome Consol](https://kinghome.by/console) | Сохранённая source-страница прямо называет серию Console и консольным типом; отдельный primary URL производителя с exact model codes не найден. |
| 154, LG ARTCOOL Gallery Premium | 1072 `A09GA2`; 1073 `A12GA2` | `cat-household` | `complete_split_system` / `сплит-система` / — | — | [Импортная страница серии](https://lg24.by/product-category/konditionery_dla_doma/artcool-gallery-premium/) | **Настенная**, не консольная: [LG A09GA2](https://www.lg.com/uk/business/hvac/residential-solutions/residential-air-conditioner/artcool-gallery/a09ga2/) указывает Wall Mounted. |
| 153, LG ARTCOOL Gallery Special | 1070 `A09GA1`; 1071 `A12GA1` | `cat-household` | `complete_split_system` / `сплит-система` / — | — | [Импортная страница серии](https://lg24.by/product-category/konditionery_dla_doma/artcool-gallery-special/) | **Настенная**, не консольная: [LG A09GA1](https://www.lg.com/uk/business/hvac/residential-solutions/residential-air-conditioner/wall-mounted/a09ga1/) указывает Wall Mounted. |
| 152, LG ARTCOOL Gallery | 1068 `A09FT`; 1069 `A12FT` | `cat-household` | `complete_split_system` / `сплит-система` / — | -10 ~ +24 °C | [Импортная страница серии](https://lg24.by/product-category/konditionery_dla_doma/artcool-gallery/) | **Настенная**, не консольная: exact LG-карточки [A09FT](https://www.lg.com/ru/air-conditioners-split-systems/lg-A09FT) и [A12FT](https://www.lg.com/it/condizionatori/a12ft/) называют их ARTCOOL Gallery/monosplit с рамкой и сменным изображением. |

Таким образом, реальная console-инвентаризация сейчас включает TCL 276 и
Kinghome 87 как готовые split-системы, а MDV 1021/1022 — только внутренние
multi-компоненты. Три LG Gallery-серии не являются console-кандидатами: это
декоративные настенные блоки с рамкой/изображением. У LG в публичных карточках
`indoor_type` отсутствует, но это пробел заполнения данных, а не основание
присвоить `console`.

Для TCL видна причина, почему смена `type` на `сплит-система` и
`indoor_type` на `настенный` не перемещает товар: во всех трёх публичных
ответах сохранён отдельный category-тег `cat-industrial`. Для ID 1431, 1429
и 1430 целевое исправление — ручная группа «Бытовые»
(`catalog_category_override=cat-household`) и `specs.indoor_type=консольный`
(производный фильтр `__filter_indoor_type=console`), при сохранении
`product_kind=complete_split_system` и `type=сплит-система`. В текущей рабочей
версии изменение формы блока не обновляет category-тег. Обозначение TCL Light
Commercial сохраняется как факт источника; размещение в бытовой группе задаёт
менеджер. Kinghome и все LG строки уже имеют
`cat-household`; для них коррекция category не требуется.

В обновлённой карточке товара поле «Группа каталога» находится в разделе
«Основное», рядом с каноническим типом. Выбор «Бытовые» и сохранение переводят
товар в эту группу; ручное решение сохраняется при повторном импорте и
нормализации. «Авто» возвращает определение по характеристикам. Форма блока
редактируется отдельно в характеристиках. Изменение кода и добавление поля в
базу сами по себе не переклассифицируют существующие товары.

## Ограничение исторических данных и безопасный follow-up

Ранее console сводился к `floor_ceiling` в MDV/Hisense parser paths и к `column`
в общей нормализации. После новой canonical логики будущие импорты сохраняют
`консольный` и filter value `console`, но уже свёрнутые записи нельзя безопасно
переклассифицировать по title или slug: это эвристика, а не первоисточник.

Безопасный отдельный follow-up: сформировать read-only план кандидатов только
по сохранённым supplier/original source URLs; для каждой строки приложить
сохранённый source URL, модель и прямое доказательство типа от производителя;
после сверки выполнить адресное исправление этих записей. В этой ветке
production backfill не выполнялся. Публичный API принимает новый indoor type
`console`; разделение бытового и полупромышленного каталога сохраняется.

## Правило taxonomy для будущих импортов

Console — это форма внутреннего блока, а не признак полупромышленной категории.
Готовая console split-система без явного system type `полупромышленный` получает
`cat-household`; явный `полупромышленный кондиционер` остаётся
`cat-industrial`; `внутренний блок` и другие признаки multi имеют приоритет и
остаются `cat-multi`. Поэтому две найденные MDV позиции сохраняются компонентами
мульти-системы, а не переклассифицируются в готовые бытовые системы.

Canonical registry теперь содержит `консольный` и typed filter value `console`.
Публичный `indoor_types=console` также принимается и фильтрует по этому значению;
это не меняет публичный UI или существующие category filters.
