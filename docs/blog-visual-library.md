# Визуальная библиотека блога MVN

Версия 1.0 · июль 2026

## 1. Задача системы

Иллюстрации должны выглядеть как главы одного инженерного атласа MVN: спокойные, точные, понятные без подписи и узнаваемые даже без логотипа. Это не набор «красивых картинок про кондиционеры», а повторяемая система для обложек, схем внутри статей, социальных карточек и будущих материалов.

Ключевой образ: **чистый современный интерьер, показанный глазами инженера**. Пространство реалистично, но слегка упрощено; технический принцип объясняется бирюзовыми потоками, тонкими контурными подсказками и одним ясным визуальным сюжетом.

## 2. Аудит текущей библиотеки

Проверено 12 опубликованных MDX-статей и 12 связанных hero-изображений из `web/public/img/blog/`.

### Что работает

- темы в большинстве случаев считываются быстро;
- светлый фон сочетается с интерфейсом сайта;
- бирюзовый уже периодически используется как смысловой цвет;
- сравнения и движение воздуха — правильный тип объяснения для HVAC-тематики.

### Что ломает цельность

| Дефект | Наблюдение | Решение библиотеки |
|---|---|---|
| Разные художественные языки | Акварель, flat vector, 3D render, почти фотография и пиктограмма находятся рядом | Один стиль: clean editorial 3D illustration с мягкими архитектурными формами и точными векторными оверлеями |
| Разная геометрия | Квадраты 1024×1024, широкие 1024×434 и 3:2 1536×1024 обрезаются в карточке 16:9 | Единый master 1600×900; значимые объекты внутри центральной safe-zone 1360×720 |
| Случайные модели блоков | Корпус, пропорции, дисплей и жалюзи меняются от статьи к статье | Один вымышленный `MVN Reference Split 01`, без логотипов и текста |
| Несогласованные потоки | Волны, ленты, тонкие линии, листья и декоративные завитки | Единый набор AirFlow: три параллельные бирюзовые линии с каплевидным концом и редкими направляющими шевронами |
| Неуправляемая типографика | Английские подписи и псевдотекст внутри изображений | Никакого текста в генерации; цифры и подписи добавляются в верстке или отдельным SVG-слоем |
| Перегруженные сцены | Некоторые изображения пытаются показать весь материал статьи сразу | Один тезис и один визуальный конфликт на обложку |
| Разные персонажи | От мультяшных героев до реалистичных людей | Люди вторичны, без портретной детализации; одинаковая пластика, нейтральная одежда |
| Слабая бренд-связь | Бирюзовый используется нерегулярно, нет постоянного знака | Бирюзовый поток, янтарный risk-marker и фирменная «точка замера» повторяются во всех сценах |

Отдельная проблема: `montagh-2-etapa.png` существует в public, но не используется текущим frontmatter. Это альтернативный визуал без роли в библиотеке; его нужно архивировать после миграции.

## 3. Ядро визуального стиля: MVN Climate Atlas

### Художественный язык

`Clean editorial 3D illustration + restrained technical overlay`.

- архитектура и предметы — мягкий 3D с матовыми материалами;
- технические смыслы — плоские тонкие линии поверх сцены;
- реализм достаточен, чтобы поверить в помещение, но без фотографического шума;
- никакой мультяшной гротескности, глянцевой рекламы или sci-fi интерфейсов;
- один кадр — один инженерный вывод.

### Камера и перспектива

- изометрическая перспектива 3/4, эквивалент 35–40 mm;
- камера на высоте 1,65 м, наклон вниз 8–12°;
- вертикали остаются вертикальными;
- основной блок расположен в верхней трети, смысловой объект — в центральной;
- сравнения делаются в одном непрерывном пространстве, а не split-screen с рамкой.

Допустимое исключение: макро-сюжеты про фильтр и запах сохраняют тот же угол света и материалы, но камера приближается до 70 mm.

### Свет

- постоянный источник: большое окно вне кадра слева сверху;
- направление: слева направо, сверху вниз под 35–40°;
- температура ключевого света 5200 K;
- мягкое заполнение справа, без черных теней;
- тень матовая, короткая, нейтрально-серая;
- бирюзовые потоки слегка светятся, но не освещают всю комнату.

### Палитра

| Роль | Цвет | HEX | Применение |
|---|---|---:|---|
| MVN Teal | основной | `#11B8B2` | воздух, активное действие, правильный путь |
| Deep Teal | контур | `#075E63` | линии, границы, холодные тени |
| Ice | фон | `#EAF7F6` | воздух, окна, вторичные плоскости |
| Warm White | база | `#F7F5F0` | стены и общий фон |
| Graphite | нейтральный | `#24343A` | техника, тонкие смысловые элементы |
| Mist Gray | архитектура | `#C9D5D5` | мебель, вторичные поверхности |
| Amber | предупреждение | `#F2A93B` | риск, тепло, нежелательный сценарий |
| Coral | авария | `#E56A5D` | только поломка/грязь/запрет, не более 5% кадра |

Соотношение в типичной сцене: 65% warm white/ice, 20% нейтральные материалы, 10% teal, до 5% amber/coral.

### Эталонный кондиционер

`MVN Reference Split 01` — вымышленная модель, одинаковая во всех бытовых сценах:

- настенный блок 880×295×210 мм по визуальным пропорциям;
- матовый теплый белый корпус, радиус углов 28 мм;
- тонкий графитовый шов снизу, одна непрерывная жалюзи;
- скрытый дисплей без читаемых цифр;
- без логотипа, кнопок, цветных вставок и декоративных полос;
- наружный блок — матовый светло-серый, круг вентилятора с 7 лопастями, одинаковая решетка.

Для полупромышленной статьи используются производные той же семьи: одинаковые материалы, радиусы, решетки и графитовые швы.

### Воздух и техническая графика

- основной поток: 3 параллельные линии толщиной 8 px в master 1600×900;
- расстояние между линиями: 12 px;
- цвет `#11B8B2`, прозрачность 72–82%;
- закругленные концы, плавный радиус, без резких зигзагов;
- направление показывают небольшие шевроны через 160–220 px, не классические стрелки;
- свежий воздух: сплошной teal;
- рециркуляция: teal с коротким штриховым фрагментом;
- теплый поток: amber с теми же геометрией и толщиной;
- нежелательный поток: coral, один перечеркнутый маркер;
- запах/грязь не изображать зелеными облаками: использовать полупрозрачные серо-коралловые частицы.

AirFlow — точный брендовый слой, а не часть свободной генерации. Генератор создает помещение, свет, технику и материалы без стрелок; три линии, шевроны, точки замера и warning-маркеры накладываются воспроизводимым векторным/детерминированным слоем. Это исключает четвертые линии, разветвления и дрейф толщины между статьями.

### Повторяющиеся элементы бренда

1. **Точка замера MVN** — маленький круг 18 px с внешним кольцом 2 px Deep Teal; обозначает место, где важен человек, температура или решение.
2. **Маркер инженерного решения** — короткая бирюзовая угловая скоба, появляющаяся у ключевого узла.
3. **Три линии AirFlow** — постоянная подпись категории, заметная хотя бы в одном месте каждого изображения.
4. **Материалы интерьера** — светлый дуб, теплые белые стены, серо-бежевый текстиль, одна живая зелень максимум.
5. **Персонаж** — при необходимости взрослый человек в графитово-синей или песочной одежде, без ярких паттернов; лицо не является центром кадра.

### Иконография

- контур 2.5 px на артборде 24×24;
- rounded line caps и углы радиусом 2 px;
- только фронтальный или изометрический вид в рамках одного набора;
- filled-формы только для маленькой точки состояния;
- teal = норма/действие, amber = внимание, coral = ошибка;
- не использовать эмодзи, material icons внутри иллюстраций, псевдо-UI и объемные значки.

## 4. Композиционная система

### Форматы

- основной hero: 1600×900, 16:9;
- retina master: 2400×1350;
- OG/social: безопасно кропается до 1200×630;
- карточка: безопасно кропается до 16:9 без потери смысла;
- мобильный кроп: центральные 70% ширины должны содержать блок и главный тезис.

### Сетка hero

- верхние 12%: свободная зона, без мелких деталей;
- центральные 76%: смысловая сцена;
- нижние 12%: только вторичные поверхности и тени;
- вокруг каждого края — 7.5% safe area;
- не более 5 крупных объектов и 2 смысловых оверлеев;
- фокус строится по диагонали: источник/проблема слева → решение/результат справа.

### Типы обложек

1. **Room story** — расположение, Wi-Fi, обогрев, приток.
2. **Technical cutaway** — фильтры, запах, монтаж.
3. **System comparison** — инвертор, мультисплит, бренды.
4. **Scale map** — BTU, полупромышленные типы.

Это четыре шаблона внутри одной системы, а не четыре разных стиля.

## 5. Базовый prompt-контракт

Каждый prompt ниже следует дополнять этим неизменным блоком:

> Create one self-contained 16:9 editorial HVAC illustration for the MVN Climate Atlas visual system. Clean restrained architectural 3D illustration with precise flat technical overlays, matte materials, warm-white and pale-ice interior, light oak and mist-gray details. Consistent three-quarter isometric camera, 38 mm lens, camera height 1.65 m, slight 10-degree downward angle, vertical lines straight. Soft daylight from upper left at 5200K, gentle short shadows, quiet premium engineering mood. Use the fictional MVN Reference Split 01: matte warm-white indoor unit with softly rounded corners, one graphite lower seam and one continuous louver, no logo and no readable display. Air movement is always shown by exactly three smooth parallel teal lines, #11B8B2, rounded ends, subtle directional chevrons; amber only for heat or caution, coral only for faults. Thin consistent deep-teal technical linework. No text, no letters, no numbers, no logos, no brand marks, no watermark, no collage, no split-screen frame, no photorealistic stock-photo look, no cartoon exaggeration, no neon sci-fi UI. Keep all essential content inside the central 85% safe area. 2400×1350 master composition.

Negative prompt для всех сцен:

> readable text, gibberish labels, typography, logo, watermark, multiple art styles, watercolor, hand-drawn sketch, flat clipart, glossy advertising render, cyberpunk, dark room, dramatic hard shadow, fisheye, extreme wide angle, dutch angle, clutter, excessive plants, floating UI, blue neon, green stink cloud, oversized arrows, inconsistent air-conditioner body, deformed architecture, extra vents, extra louvers

## 6. Концепции и prompts для каждой статьи

### 6.1 Фильтры в кондиционере

**Концепция:** «Фильтр важен, но он не волшебный». Макро-разрез одного эталонного блока: крупная сетка задерживает пыль, маленькая дополнительная вставка занимает вторичное место. Чистый поток выходит в комнату; никаких вееров из разноцветных фильтров.

**Композиция:** блок слева сверху в разрезе; сетка в центре; частицы до фильтра — серые, после — единичные; поток направлен вправо вниз. Бирюзовая скоба выделяет моющуюся сетку.

**Prompt:**

> [BASE CONTRACT] Close technical cutaway of the MVN Reference Split 01 in a clean living room. The front panel is gently lifted, revealing one large washable mesh filter as the dominant element and one much smaller optional charcoal insert as a secondary element. Sparse neutral dust particles approach the mesh and are visibly caught; clean air leaves through the lower louver as three teal airflow lines. The heat exchanger remains visible but simplified, clean, and credible. The visual message is practical maintenance over marketing magic. 70 mm close perspective while preserving the same upper-left daylight and material language. No array of colorful filters, no medical claims, no microscopic germs.

### 6.2 Где нельзя ставить кондиционер

**Концепция:** «Поток должен обходить человека». Спальня с блоком сбоку от изголовья: правильный бирюзовый поток идет вдоль комнаты; полупрозрачный coral ghost-position напротив кровати показывает ошибку.

**Композиция:** кровать справа внизу, рабочее место дальше; правильный блок слева сверху; ошибочная позиция — только тонкий контур, без второго физического прибора.

**Prompt:**

> [BASE CONTRACT] Calm modern bedroom viewed in three-quarter perspective. A correctly placed MVN Reference Split 01 sits on the side wall near the headboard and sends three smooth teal airflow lines along the room, safely past the sleeping zone. A single subtle coral outline on the opposite wall indicates the wrong placement that would blow directly across the bed, with one restrained crossed marker. Include the MVN measurement point near pillow height. Clear visual hierarchy, lots of clean wall space, no confused person, no seven separate warning icons.

### 6.3 Инвертор или On/Off

**Концепция:** «Ровная линия против температурных качелей». Один интерьер плавно переходит из спокойной зоны в зону циклов, но без split-screen. Два одинаковых блока; у инвертора поток плавный, у On/Off — прерывистый и amber.

**Композиция:** два одинаковых фрагмента стены соединены общей линией пола; слева стабильная teal wave, справа ступенчатые amber импульсы; человек показан один раз в центре как точка сравнения.

**Prompt:**

> [BASE CONTRACT] One continuous bedroom-studio environment comparing two operating behaviors without a dividing frame. On the left, an identical MVN Reference Split 01 produces a gentle continuous teal airflow and a thin stable teal temperature curve. On the right, the same unit produces intermittent amber airflow pulses and a restrained stepped temperature curve. One neutral seated person at the center provides human scale, comfortable toward the stable side. The units must be visually identical; only operating behavior differs. No labels, no lightning bolts, no angry cartoon faces, no energy-saving claims.

### 6.4 Как рассчитать мощность: BTU

**Концепция:** «Размер комнаты плюс теплопритоки». Одна комната как инженерная модель: площадь пола, солнце, окно, человек и техника влияют на бирюзовую зону комфорта.

**Композиция:** изометрическая комната с едва заметной модульной сеткой пола; кондиционер слева; amber теплопритоки от панорамного окна и техники; teal покрытие комнаты. Чисел внутри изображения нет.

**Prompt:**

> [BASE CONTRACT] Isometric cutaway of one modern living room as a clean capacity-planning model. A subtle floor grid communicates room area without any numbers. The MVN Reference Split 01 creates a broad balanced teal comfort field. Warm sunlight through a large window, one seated person, and a television each create restrained amber heat cues that add load. A small adjoining open kitchen adds one additional amber cue. The scene should instantly communicate that room size is the starting point but sun, people, equipment, and layout affect sizing. No calculator screen, no readable digits, no formula text.

### 6.5 Монтаж в два этапа

**Концепция:** «Сначала скрытая инженерия, потом чистый интерьер». Одна стена в фазовом переходе: слева открытая штроба с трассой и дренажным уклоном, справа та же стена после отделки с блоком.

**Композиция:** единая стена, вертикальная граница материала без рамки; трасса строго геометрична; справа готовый блок и мягкий поток. Цветовая логика: скрытая инженерия Deep Teal, готовый воздух Teal.

**Prompt:**

> [BASE CONTRACT] One continuous apartment wall shown in a seamless before-to-after material transition. The left portion is unfinished warm-gray plaster with one precise vertical chase revealing paired copper lines, insulation, electrical cable, and a drain line with a clearly visible gentle downward slope; the right portion is the same finished warm-white wall with the MVN Reference Split 01 installed cleanly and three teal airflow lines entering the room. Include a compact protected pipe bundle exiting at the exact future unit position. No workers, no tools scattered everywhere, no text such as stage one or stage two, no impossible pipe bends.

### 6.6 Мультисплит или несколько сплит-систем

**Концепция:** «Одна общая точка отказа против независимости». Разрез небольшого дома: слева один наружный блок связан с тремя комнатами, справа три независимых пары. Не утверждать визуально, что один вариант всегда лучше.

**Композиция:** один непрерывный фасад-дом с двумя инженерными вариантами; бирюзовые трассы одинаковой толщины; amber ring только отмечает общую точку, не выносит вердикт.

**Prompt:**

> [BASE CONTRACT] Clean architectural cutaway of a compact two-level home comparing system topology in one continuous scene. The left half uses one consistent large outdoor unit connected by tidy deep-teal line routes to three matching indoor units; a subtle amber ring identifies the shared outdoor dependency. The right half uses three separate smaller outdoor units, each connected to one matching indoor unit, showing independent paths and more facade equipment. Keep both options equally polished and credible, with no winner badge, no labels, no broken equipment, no exaggerated cost symbols.

### 6.7 Обогрев кондиционером

**Концепция:** «Тепло переносится, а не рождается из спирали». Осенняя гостиная: наружный холодный воздух, наружный блок и теплый amber поток внутри; teal петля показывает перенос энергии через стену.

**Композиция:** разрез фасада, улица слева, комната справа; дерево с несколькими осенними листьями — единственный сезонный знак; человек не обязателен.

**Prompt:**

> [BASE CONTRACT] Elegant facade cutaway in early autumn, exterior on the left and a calm living room on the right. The matching outdoor unit extracts low-grade heat from cool outside air, represented by a restrained teal energy loop passing through the wall to the MVN Reference Split 01. Inside, the unit releases three smooth amber airflow lines into the occupied zone. One small tree with muted autumn leaves sets the season. The image should explain heat transfer rather than an electric heating coil. No snowstorm, no flames, no glowing red appliance, no cozy lifestyle advertising cliché.

### 6.8 Почему появился запах

**Концепция:** «Источник внутри, не в воздухе комнаты». Макро-разрез загрязненного теплообменника, крыльчатки и дренажного поддона; частицы выходят вместе с потоком. Рядом маленькая чистая зона после обслуживания.

**Композиция:** крупный блок занимает верхнюю половину; coral-gray particles возникают только после грязных узлов; человек отсутствует — не превращаем техническую тему в карикатуру.

**Prompt:**

> [BASE CONTRACT] Close technical cutaway of the MVN Reference Split 01 showing the actual odor sources: a lightly contaminated evaporator surface, dust on the cross-flow fan, moisture in the drain pan, and one partially obstructed drain outlet. Three normal teal airflow lines pass through these internal areas and pick up sparse translucent gray-coral particles before leaving the louver. A small clean serviced section provides a quiet contrast through material cleanliness, not a separate panel. Credible HVAC internals, restrained hygiene message. No person holding nose, no green cloud, no mushrooms, no monsters, no horror imagery.

### 6.9 Полупромышленные кондиционеры

**Концепция:** «Тип следует за пространством». Одно архитектурное здание с четырьмя логичными зонами: канал в потолке, кассета в open-space, напольно-потолочный блок в длинном зале, колонный в высоком помещении.

**Композиция:** разрез 2×2 без жестких рамок; единая архитектура и свет; каждый тип отличается направлением AirFlow, а не декоративным стилем.

**Prompt:**

> [BASE CONTRACT] Refined isometric cutaway of one coherent small commercial building with four connected zones, each demonstrating a different indoor-unit type from the same MVN product family. A concealed ducted unit serves two ceiling diffusers in a meeting area; a four-way cassette serves an open office; a floor-ceiling unit throws air along a long studio; a slim floor-standing column unit serves a tall retail zone. Use the same matte warm-white bodies, graphite seams, teal airflow language, architectural materials, and upper-left light throughout. No labels, no showroom lineup, no salesperson, no random residential wall splits.

### 6.10 Кондиционер с притоком воздуха

**Концепция:** «Небольшой приток плюс рециркуляция». Разрез внешней стены: тонкая teal линия свежего воздуха входит с улицы и соединяется с более крупной петлей рециркуляции внутри.

**Композиция:** окно и улица слева, блок на внутренней стене; два типа линий различаются только паттерном, а не цветовой радугой; точка замера у кровати показывает человека как цель.

**Prompt:**

> [BASE CONTRACT] Bedroom facade cutaway explaining limited fresh-air intake. A thin solid teal line enters from outdoors through a small dedicated intake path and joins a much larger dashed teal recirculation loop at the MVN Reference Split 01. The combined airflow leaves as the standard three teal lines toward the room, while a subtle MVN measurement point near the bed indicates the occupied breathing zone. The outdoor opening remains modest in scale, making clear that intake supplements rather than replaces ventilation. No open window gust, no leaves, no oxygen symbols, no oversized fresh-air pipe, no miraculous purification claim.

### 6.11 Бренды кондиционеров 2026

**Концепция:** «Выбирают серию и поддержку, а не наклейку». Несколько одинаково нейтральных блоков стоят не на пьедестале, а на инженерной карте критериев: тишина, рабочий диапазон, сервис, наличие деталей — через абстрактные иконки без текста.

**Композиция:** один эталонный блок в центре; за ним три варианта внутренней конструкции/класса материала как глубинные слои; вокруг четыре тонких иконографических маркера. Нет рейтинговой лестницы.

**Prompt:**

> [BASE CONTRACT] One calm editorial product-analysis scene on a warm-white architectural workbench. A central unbranded MVN Reference Split 01 is shown with three restrained exploded material layers behind it: casing quality, fan and heat exchanger, control electronics. Four minimal deep-teal outline symbols surround the analysis at equal visual weight: quiet airflow, cold-weather range, service tool, available spare component. In the distant background, several neutral unbranded unit silhouettes share similar outer shapes, reinforcing that the specific series and support matter more than a sticker. No podium, no ranking staircase, no crowns, no brand logos, no readable labels, no shopping bags.

### 6.12 Wi-Fi в кондиционере

**Концепция:** «Полезный сценарий, а не гаджет ради гаджета». Человек возвращается домой; через телефон запускает кондиционер заранее, а teal поток уже формирует комфортную зону.

**Композиция:** прихожая слева, гостиная справа; телефон показан с простым абстрактным круглым control-state без UI и текста; одна тонкая пунктирная связь до блока.

**Prompt:**

> [BASE CONTRACT] Modern apartment arrival scene in one continuous interior. A person enters from a warm sunlit hallway while the living room is already comfortable: the MVN Reference Split 01 produces three calm teal airflow lines across the occupied zone. The person holds a phone showing only one abstract teal circular control state with no readable interface. A thin dotted deep-teal connection line links phone and indoor unit. Include a subtle amber heat haze outside the open entry area to explain the useful before-arrival scenario. No giant smartphone, no app logo, no voice-assistant brand, no hologram, no floating interface panels.

## 7. Внутристатейные иллюстрации

Hero отвечает на один тезис. Детальные доказательства выносятся в body-иллюстрации трех типов:

- **detail cutaway** — узел крупно, 4:3, без интерьера;
- **decision diagram** — два сценария в едином пространстве, 16:9;
- **maintenance step** — рука + один объект + одно действие, 4:3.

Для статьи о фильтрах существующие фотографии конкретных фильтров допустимо оставить как фактические примеры, но отделить их от брендовых иллюстраций: одинаковый светло-серый фон, одинаковый crop 4:3, единая подпись в HTML. Не стилизовать реальные продуктовые детали так, чтобы потерять достоверность.

## 8. Производственный процесс

1. Генерировать сначала 3 calibration-кадра: размещение, монтаж, запах. Они проверяют room story, cutaway и warning-сценарий.
2. Утвердить эталонный блок, свет, толщину AirFlow и уровень 3D-реализма.
3. Зафиксировать удачный seed/reference image и использовать его как style reference для всей серии.
4. Генерировать базовые сцены без стрелок, точек замера и warning-графики; накладывать их из общего точного overlay-компонента.
5. Генерировать остальные 9 hero по одному, не пакетной случайной серией.
6. Удалять весь сгенерированный текст; необходимые числа и подписи добавлять отдельным SVG/HTML-слоем.
7. Проверять thumbnail на ширине 360 px: тема должна считываться без заголовка.
8. Экспортировать AVIF + WebP; PNG хранить только как production master.
9. После замены удалить неиспользуемые legacy-файлы и проверить `npm run audit:theme` и `npm run build`.

### Имена файлов

`/img/blog/v2/{slug}-hero.webp` и `/img/blog/v2/{slug}-{diagram-name}.webp`.

### Критерии приемки каждого hero

- соответствует теме без текста;
- эталонный корпус не меняет форму;
- свет идет слева сверху;
- AirFlow состоит из трех линий установленной толщины;
- teal не превращается в синий или зеленый;
- нет брендов, псевдотекста и лишней иконографии;
- работает в 16:9 и безопасно кропается до 1200×630;
- главный объект различим на карточке 360×203;
- один кадр объясняет один тезис;
- визуально совпадает минимум с двумя calibration-кадрами.

## 9. Рекомендованный пилот

Для первого production-прохода нужны ровно три изображения:

1. «Где нельзя ставить» — проверяет интерьер, человека и движение воздуха.
2. «Монтаж в два этапа» — проверяет техническую точность и cutaway.
3. «Почему появился запах» — проверяет warning-палитру без дешевой карикатуры.

Если эти три кадра выглядят как одна семья, система выдержит остальные девять. Если нет — нужно править master-style, а не вручную «дотягивать» каждую картинку разными фильтрами.
