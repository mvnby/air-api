# Растровая библиотека карточек услуг MVN

Версия 3 · июль 2026

## Назначение

Серия для `/services/` продолжает визуальный язык новых обложек блога: одна реалистичная архитектурная сцена объясняет одну услугу без подписи внутри изображения. Это не декоративные фотографии и не условные пиктограммы. Каждый кадр показывает реальную операцию или инженерную связь, которую клиент узнаёт до чтения карточки.

Публикационный формат: WebP `1672×941`, `16:9`. Все важные детали должны оставаться в центральных 85% кадра и читаться при ширине карточки 360 px.

## Общий prompt-контракт

> Create one self-contained 16:9 editorial HVAC service-card illustration for the MVN Climate Atlas visual system. Clean restrained photorealistic architectural 3D scene with precise minimal technical overlays; matte warm-white and pale-ice architecture, light oak and mist-gray details. Three-quarter camera, 38 mm lens, camera height 1.65 m, slight 10-degree downward angle, straight verticals. Soft daylight from upper left at 5200K, gentle short shadows, quiet premium engineering mood. Use the fictional MVN Reference Split 01: matte warm-white indoor unit with softly rounded corners, one graphite lower seam and one continuous louver, no logo and no readable display, mounted 10–20 cm below the ceiling. Outdoor unit when shown: matte light gray, credible fan grille and brackets. Air movement appears only when technically meaningful and is always exactly three smooth parallel turquoise lines, #11B8B2. Deep teal is used for technical linework, amber only for heat, caution or standby, coral only for a localized fault. No text, letters, numbers, logos, brand marks, watermark, UI, collage, split-screen frame, cartoon, glossy advertising render, cyberpunk, extreme wide angle, clutter, impossible pipe routes, extra louvers or oversized arrows. Keep all essential content inside the central 85% safe area and make the story instantly readable at service-card size.

## Манифест сюжетов

| ID | Файл | Визуальный вывод | Техническая проверка |
|---|---|---|---|
| `preinstallation` | `/img/services/v3/preinstallation.webp` | Коммуникации прячут до чистовой отделки | блок под потолком; трасса входит снизу слева; дренаж ниже труб и с уклоном |
| `installation` | `/img/services/v3/installation.webp` | Внутренний и наружный блок образуют готовую систему | правдоподобный проход стены; аккуратная парная трасса; ровно три линии воздуха |
| `dismantling` | `/img/services/v3/dismantling.webp` | Блок снимают безопасно, без выпуска хладагента | блок снимается с пластины; наружный блок закреплён; соединение локализовано, без облака газа |
| `maintenance` | `/img/services/v3/maintenance.webp` | Обслуживание — это глубокая чистка узлов и дренажа | сетка, теплообменник, тангенциальная крыльчатка и поддон; дренаж не направлен в комнату |
| `repair` | `/img/services/v3/repair.webp` | Ремонт начинается с измерения и поиска причины | прибор диагностики; один локальный fault-marker; без искр и постановочной аварии |
| `vrf` | `/img/services/v3/vrf.webp` | Одна спроектированная система обслуживает несколько зон | парная магистраль; Y/REFNET-разветвления; не отдельный home-run к каждой комнате |
| `server-room` | `/img/services/v3/server-room.webp` | Для серверной важны основной блок, резерв и контроль | активен один блок; холод идёт к фронту стойки; тепло выходит сзади; резерв не дует |

## Scene prompts

Каждый scene prompt добавляется после общего контракта. Референсы используются только для стиля и технического языка, а не для копирования композиции.

### Закладка коммуникаций

> Apartment renovation in progress, with a clean wall cutaway and unfinished plaster edge on the left and a finished warm minimalist room on the right. Show the paired insulated copper refrigerant lines, cable and drain inside the chase, turning 90 degrees toward and entering the lower-left edge of the indoor unit. The drain stays below the pipes, is continuous and visibly slopes away toward the wall. One clear story: the hidden route is installed before finish. No worker required, no decorative airflow, no pipe dropping below the unit and then going toward the ceiling.

### Монтаж кондиционера

> Warm modern living room in one continuous interior/exterior cutaway. Show the indoor unit high below the ceiling, the outdoor unit on the exterior side or ledge, and a neat short route through the wall entering the lower-left edge of the indoor unit. The route is plausible and tidy. Exactly three turquoise airflow lines leave the lower louver and arc safely through open room space. The visual story is a complete professionally installed split system, with no scattered tools and no impossible penetrations.

### Демонтаж кондиционера

> In one continuous architectural cutaway, a technician in neutral graphite and sand workwear safely lifts the indoor split unit away from its mounting plate. On the exterior side of the same wall, the matching outdoor unit remains secured on brackets while its service valves are closed and the paired refrigerant lines are neatly isolated. Show a small amber caution marker only at the service connection. The message is safe removal for replacement or relocation while preserving refrigerant. No vapor, broken pipes, falling equipment, destruction or decorative airflow.

### Обслуживание кондиционера

> Clear close technical service scene with the front of the wall split open. Show the large washable mesh filter, heat exchanger, tangential cross-flow fan and drain tray. A technician in neutral workwear performs careful deep cleaning using a protective wash cover and compact cleaning nozzle. The drain routes down or into the wall, never toward the viewer. Exactly three restrained teal clean-air lines leave the serviced lower louver. No dirt cloud, axial indoor fan or repair instruments.

### Ремонт кондиционера

> Warm minimalist interior with the installed wall split high below the ceiling. A technician in neutral workwear diagnoses a fault using a multimeter or test instrument. A small localized coral marker identifies one problem area and a subtle teal measurement point shows the diagnostic action. The service panel may be open, but the equipment remains installed. No sparks, refrigerant cloud, unsafe exposed-wire handling or oversized warning symbol.

### VRF и мультизональная система

> Clean cutaway of a small commercial office or hotel in one continuous scene. Show one credible modular VRF outdoor unit or compact bank outside or on the roof, a paired main gas/liquid refrigerant route entering the building, and technically plausible Y/REFNET branches feeding several indoor units across distinct zones. The branch topology is the central visual: a paired trunk, not one separate home-run from the outdoor unit to every room. Use minimal teal and deep-teal overlay and no decorative airflow overload.

### Серверная

> Realistic small server room with one rack clearly showing front intake and rear exhaust sides, one active cooling unit, one reserve unit mounted high, and an independent temperature sensor point. Only the active unit sends exactly three solid teal cold-air lines toward the rack front intake. Hot air leaves the rack rear as restrained amber lines. The reserve unit is visibly inactive with a subtle amber dashed state marker and never blows. No airflow outside the room, no two active units, no text and no sci-fi blue neon.

## Проверка серии

1. Сюжет понятен без заголовка и не подменяется абстрактным символом.
2. Внутренние блоки находятся в 10–20 см от потолка.
3. Трасса входит в нижний левый край внутреннего блока, если соединение видно.
4. Дренаж не направлен в комнату и имеет правдоподобный отвод.
5. Тангенциальная крыльчатка не заменяется осевым вентилятором.
6. Воздушный поток содержит ровно три линии и появляется только по смыслу.
7. В VRF видна магистраль с разветвлениями, в серверной — раздельные активный и резервный контуры.
8. Нет текста, логотипов, псевдоинтерфейса и случайных моделей оборудования.
9. Полный кадр читается на desktop и mobile без специального бокового кропа.
