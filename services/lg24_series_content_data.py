"""Static LG series and reusable feature seeds for lg24.by content import."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lg24SeriesSeed:
    title: str
    source_url: str
    match_slugs: tuple[str, ...]
    tagline: str
    short_description: str
    description: str
    fallback_features: tuple[str, ...]


@dataclass(frozen=True)
class LgBrandFeatureSeed:
    slug: str
    title: str
    text: str
    icon: str
    aliases: tuple[str, ...]
    keywords: tuple[str, ...]


SERIES_SEEDS: tuple[Lg24SeriesSeed, ...] = (
    Lg24SeriesSeed(
        title="Deluxe Pro",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/deluxe-pro/",
        match_slugs=("deluxe-pro",),
        tagline="Премиальная инверторная серия LG",
        short_description="Тихая серия с Dual Inverter, контролем энергопотребления и управлением через LG ThinQ.",
        description=(
            "Deluxe Pro подходит для помещений, где важны высокая энергоэффективность, "
            "низкий шум и аккуратный современный дизайн. По данным LG24, серия делает "
            "упор на Dual Inverter, контроль потребления электроэнергии, чистый воздух "
            "и Wi-Fi/голосовое управление через LG SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Контроль потребления электроэнергии",
            "Чистый воздух и максимальный комфорт",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="EVO Max",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/evo_max/",
        match_slugs=("evo-max", "evomax"),
        tagline="Инвертор LG с расширенной очисткой воздуха",
        short_description="Серия с Dual Inverter, Plasmaster Ionizer+, UVnano, Allergy Filter и Wi-Fi.",
        description=(
            "EVO Max — одна из наиболее насыщенных бытовых линеек LG на LG24: помимо "
            "экономичной инверторной работы здесь заявлены ионизация Plasmaster Ionizer+, "
            "UVnano, Allergy Filter, низкий шум и управление через приложение."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Plasmaster Ionizer+",
            "UVnano",
            "Allergy Filter",
            "Экономия электроэнергии до 70%",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="ECO Smart",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/eco-smart/",
        match_slugs=("eco-smart",),
        tagline="Практичная инверторная серия LG",
        short_description="Инверторная серия с Allergy Filter, тихой работой и управлением LG SmartThinQ.",
        description=(
            "ECO Smart — массовая бытовая серия LG с понятным набором функций: "
            "Dual Inverter, Allergy Filter, экономичная работа, низкий шум и управление "
            "через Wi-Fi/голосовые сценарии LG SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Allergy Filter",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="LOOK Smart",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/look_smart/",
        match_slugs=("look-smart", "look"),
        tagline="Инвертор LG для базового комфорта",
        short_description="Серия с Dual Inverter, Allergy Filter, быстрым охлаждением и эффективным нагревом.",
        description=(
            "LOOK Smart закрывает базовые бытовые задачи без лишней сложности: "
            "экономичное охлаждение и обогрев, Allergy Filter, быстрый выход на режим "
            "и низкий уровень шума."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Allergy Filter",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Быстрое охлаждение и эффективный нагрев",
        ),
    ),
    Lg24SeriesSeed(
        title="ARTCOOL Gallery",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/artcool-gallery/",
        match_slugs=("artcool-gallery",),
        tagline="Дизайнерская серия с заменяемым изображением",
        short_description="ARTCOOL Gallery совмещает инверторную работу LG и декоративную фронтальную панель.",
        description=(
            "ARTCOOL Gallery — дизайнерская серия LG: кондиционер работает как бытовая "
            "сплит-система, но фронтальная панель используется как интерьерный объект "
            "с возможностью смены изображения."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Ультратонкий дизайн со сменным изображением",
            "Контроль потребления электроэнергии",
            "Чистый воздух и максимальный комфорт",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="ARTCOOL Gallery Special",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/artcool-gallery-special/",
        match_slugs=("artcool-gallery-special",),
        tagline="Специальная версия ARTCOOL Gallery",
        short_description="Дизайнерская серия Gallery Special с инвертором LG и сменным изображением.",
        description=(
            "ARTCOOL Gallery Special развивает идею Gallery: серия рассчитана на "
            "интерьеры, где внешний вид внутреннего блока так же важен, как охлаждение, "
            "обогрев и управление через приложение."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Ультратонкий дизайн со сменным изображением",
            "Контроль потребления электроэнергии",
            "Чистый воздух и максимальный комфорт",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="ARTCOOL Gallery Premium",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/artcool-gallery-premium/",
        match_slugs=("artcool-gallery-premium",),
        tagline="Премиальная версия ARTCOOL Gallery",
        short_description="Интерьерная серия Gallery Premium с Dual Inverter и управлением LG ThinQ.",
        description=(
            "ARTCOOL Gallery Premium — верхняя дизайнерская линейка Gallery. На LG24 "
            "для нее заявлены Dual Inverter, сменное изображение на передней панели, "
            "контроль потребления, чистый воздух и SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Ультратонкий дизайн со сменным изображением",
            "Контроль потребления электроэнергии",
            "Чистый воздух и максимальный комфорт",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="ARTCOOL Mirror",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/artcool-mirror/",
        match_slugs=("artcool-mirror",),
        tagline="Инвертор LG в зеркальном дизайне",
        short_description="ARTCOOL Mirror сочетает зеркальную панель, Dual Inverter, ионизацию и Wi-Fi.",
        description=(
            "ARTCOOL Mirror — серия для интерьеров, где обычный белый внутренний блок "
            "не подходит визуально. По данным LG24, линейка сочетает стильный дизайн, "
            "Dual Inverter, Plasmaster Ionizer+, экономию энергии и SmartThinQ."
        ),
        fallback_features=(
            "Стильный дизайн ARTCOOL",
            "Dual Inverter компрессор с 10-летней гарантией",
            "Plasmaster Ionizer+",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="Objet Green",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/objet_green/",
        match_slugs=("objet-green", "object-green"),
        tagline="Цветная дизайнерская серия LG Objet",
        short_description="Objet Green — дизайнерский инвертор LG с ионизацией, низким шумом и SmartThinQ.",
        description=(
            "Objet Green делает акцент на цвете и дизайне внутреннего блока, сохраняя "
            "ключевые функции LG: Dual Inverter, Plasmaster Ionizer+, экономичную работу, "
            "низкий шум и управление через LG SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Plasmaster Ionizer+",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="Objet Beige",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/objet_beige/",
        match_slugs=("objet-beige", "object-beige"),
        tagline="Бежевая дизайнерская серия LG Objet",
        short_description="Objet Beige — интерьерная серия LG с инвертором, ионизацией и SmartThinQ.",
        description=(
            "Objet Beige подходит для спокойных светлых интерьеров, где нужен не только "
            "климат, но и аккуратное попадание блока в дизайн комнаты. На LG24 серия "
            "описана через Dual Inverter, Plasmaster Ionizer+, экономию и SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Plasmaster Ionizer+",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="DUALCOOL Premium",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/dualcool-premium/",
        match_slugs=("dualcool-premium", "dual-cool-premium"),
        tagline="Премиальная бытовая серия LG DUALCOOL",
        short_description="DUALCOOL Premium соединяет Dual Inverter, контроль энергии, чистый воздух и Wi-Fi.",
        description=(
            "DUALCOOL Premium — бытовая премиальная серия LG с акцентом на экономичный "
            "инвертор, комфортный воздух, контроль потребления и управление через "
            "LG SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Контроль потребления электроэнергии",
            "Чистый воздух и максимальный комфорт",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="ECO",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/eco/",
        match_slugs=("eco",),
        tagline="Базовая инверторная серия LG",
        short_description="ECO — простая серия LG с Allergy Filter, экономичной работой и быстрым выходом на режим.",
        description=(
            "ECO — базовая бытовая серия LG для стандартных помещений. В карточках LG24 "
            "для нее выделены Dual Inverter, Allergy Filter, экономия электроэнергии, "
            "низкий шум, быстрое охлаждение и эффективный нагрев."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Allergy Filter",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Быстрое охлаждение и эффективный нагрев",
        ),
    ),
    Lg24SeriesSeed(
        title="PuriCare",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/puricare/",
        match_slugs=("puricare", "puri-care"),
        tagline="LG с усиленным акцентом на качество воздуха",
        short_description="PuriCare — инверторная серия с ионизацией, тихой работой и SmartThinQ.",
        description=(
            "PuriCare логично выделять покупателям, которым важны не только охлаждение "
            "и обогрев, но и качество воздуха. На LG24 для серии заявлены Dual Inverter, "
            "Plasmaster Ionizer+, экономия, низкий шум и SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Plasmaster Ionizer+",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="PROCOOL",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/procool/",
        match_slugs=("procool", "pro-cool"),
        tagline="Тихий инвертор LG с ионизацией",
        short_description="PROCOOL сочетает Dual Inverter, Plasmaster Ionizer+, низкий шум и SmartThinQ.",
        description=(
            "PROCOOL — бытовая серия LG с низким уровнем шума и расширенной очисткой "
            "воздуха. По LG24, серия включает Dual Inverter, Plasmaster Ionizer+, "
            "экономию электроэнергии и управление через LG SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Plasmaster Ionizer+",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="EVOCOOL",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/evocool/",
        match_slugs=("evocool", "evo-cool"),
        tagline="Инвертор LG с ионизацией и Wi-Fi",
        short_description="EVOCOOL — серия с Dual Inverter, Plasmaster Ionizer+, низким шумом и SmartThinQ.",
        description=(
            "EVOCOOL находится между базовыми и более насыщенными линейками LG: "
            "в карточках LG24 заявлены Dual Inverter, Plasmaster Ionizer+, экономия "
            "электроэнергии, низкий шум и управление через приложение."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Plasmaster Ionizer+",
            "Экономия электроэнергии до 70%",
            "Низкий уровень шума",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="Smart Line",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/smart_line/",
        match_slugs=("smart-line",),
        tagline="Бытовая инверторная серия LG",
        short_description="Smart Line — инвертор LG с экономичной работой, низким шумом и SmartThinQ.",
        description=(
            "Smart Line — спокойная бытовая серия LG для стандартных задач охлаждения "
            "и обогрева. LG24 выделяет Dual Inverter, экономию электроэнергии, низкий "
            "шум и Wi-Fi/голосовое управление через LG SmartThinQ."
        ),
        fallback_features=(
            "Dual Inverter компрессор с 10-летней гарантией",
            "Экономия электроэнергии до 70%",
            "Бесшумная работа",
            "Wi-Fi и голосовое управление LG SmartThinQ",
        ),
    ),
    Lg24SeriesSeed(
        title="Ultra Inverter",
        source_url="https://lg24.by/product/4-potochnyj-kassetnyj-tip-ultra-inverter-ct09r-uu09wr/",
        match_slugs=("ultra-inverter",),
        tagline="Коммерческая серия LG для кассетных, канальных и потолочных систем",
        short_description="Ultra Inverter — коммерческие блоки LG с распределением воздуха, дренажным насосом и корейской сборкой.",
        description=(
            "Ultra Inverter закрывает коммерческие задачи: кассетные, канальные, "
            "потолочные и колонные решения для офисов, торговых помещений и объектов "
            "с требованием к равномерному воздухообмену."
        ),
        fallback_features=(
            "Равномерное распределение воздуха",
            "Индивидуальное управление створками",
            "Встроенный дренажный насос",
            "Упрощенный монтаж",
            "Сделано в Южной Корее",
        ),
    ),
    Lg24SeriesSeed(
        title="Ultra Inverter R32",
        source_url="https://lg24.by/product/srednenapornyj-kanalnyj-tip-cm18r-cm18r/",
        match_slugs=("ultra-inverter-r32",),
        tagline="Коммерческая инверторная серия LG на R32",
        short_description="Ultra Inverter R32 ориентирована на канальные и зональные коммерческие решения LG.",
        description=(
            "Ultra Inverter R32 — коммерческая линейка LG с хладагентом R32. В карточках "
            "LG24 для канальных моделей выделены поддержание расчетного расхода воздуха, "
            "зональное управление и возможность работы на несколько воздуховодов."
        ),
        fallback_features=(
            "Поддержание расчетного расхода воздуха",
            "Зональное управление",
            "До 9 воздуховодов с одинаковыми параметрами",
            "Дренажный насос опционально",
            "Сделано в Южной Корее",
        ),
    ),
    Lg24SeriesSeed(
        title="Smart Inverter",
        source_url="https://lg24.by/product/4-potochnyj-kassetnyj-tip-smart-inverter-ut18wc-uu18wc/",
        match_slugs=("smart-inverter",),
        tagline="Коммерческая инверторная серия LG",
        short_description="Smart Inverter — коммерческие блоки LG с 4-сторонним распределением воздуха и удобным монтажом.",
        description=(
            "Smart Inverter — коммерческая серия LG для объектов, где важны равномерное "
            "распределение воздуха, обслуживание с потолка и предсказуемый монтаж. "
            "LG24 отдельно отмечает управление створками, 4-сторонний поток и дренажный насос."
        ),
        fallback_features=(
            "Индивидуальное управление створками",
            "Равномерное распределение воздуха в 4 стороны",
            "Возможность установки на большой высоте",
            "Упрощенный монтаж",
            "Встроенный дренажный насос",
        ),
    ),
)


BRAND_FEATURE_SEEDS: tuple[LgBrandFeatureSeed, ...] = (
    LgBrandFeatureSeed(
        slug="dual-inverter",
        title="Dual Inverter",
        text="Инверторный компрессор LG быстрее выходит на режим, работает тише и экономит электроэнергию по сравнению с обычным компрессором.",
        icon="settings_suggest",
        aliases=("Dual Inverter компрессор", "Инверторный компрессор LG"),
        keywords=("dual inverter", "инверторный компрессор", "10-летней гарантией"),
    ),
    LgBrandFeatureSeed(
        slug="energy-control",
        title="Active Energy Control",
        text="Режимы контроля энергопотребления позволяют ограничивать расход электроэнергии и управлять эффективностью охлаждения.",
        icon="energy_savings_leaf",
        aliases=("Контроль потребления электроэнергии", "Active Energy Control"),
        keywords=("active energy control", "контроль потребления", "экономия электроэнергии", "энергосбереж"),
    ),
    LgBrandFeatureSeed(
        slug="lg-thinq",
        title="LG ThinQ / SmartThinQ",
        text="Wi-Fi и приложение LG ThinQ/SmartThinQ дают удаленное управление, мониторинг и голосовые сценарии.",
        icon="wifi",
        aliases=("SmartThinQ", "LG ThinQ", "Wi-Fi управление"),
        keywords=("smartthinq", "lg thinq", "wi-fi", "wifi", "голосовое управление"),
    ),
    LgBrandFeatureSeed(
        slug="allergy-filter",
        title="Allergy Filter",
        text="Фильтр Allergy Filter помогает задерживать аллергены и поддерживать более чистый воздух в помещении.",
        icon="filter_alt",
        aliases=("Аллергенный фильтр", "Allergy Filter"),
        keywords=("allergy filter", "аллерген", "здоровый микроклимат"),
    ),
    LgBrandFeatureSeed(
        slug="plasmaster-ionizer",
        title="Plasmaster Ionizer+",
        text="Ионизатор Plasmaster Ionizer+ используется LG для дополнительной обработки воздуха и снижения количества бактерий.",
        icon="air",
        aliases=("Ионизатор", "Plasmaster Ionizer+"),
        keywords=("plasmaster", "ionizer", "ионизатор", "ионизации воздуха"),
    ),
    LgBrandFeatureSeed(
        slug="uvnano",
        title="UVnano",
        text="UVnano использует УФ-лампу для обеззараживания внутренних элементов и дополнительной гигиены воздуха.",
        icon="shield",
        aliases=("UVnano", "УФ-лампа"),
        keywords=("uvnano", "уф-ламп", "ультрафиолет"),
    ),
    LgBrandFeatureSeed(
        slug="gold-fin",
        title="Gold Fin",
        text="Покрытие Gold Fin защищает теплообменник от коррозии и помогает продлить срок службы наружного блока.",
        icon="shield",
        aliases=("Gold Fin", "Голд Фин"),
        keywords=("gold fin", "голд фин", "защищает теплообменник", "корроз"),
    ),
    LgBrandFeatureSeed(
        slug="low-noise",
        title="Низкий уровень шума",
        text="Тихая работа внутреннего блока важна для спален, кабинетов и других помещений, где кондиционер работает долго.",
        icon="volume_down",
        aliases=("Бесшумная работа", "Низкий уровень шума"),
        keywords=("бесшум", "низкий уровень шума", "19 дб", "21 дб", "22 дб"),
    ),
    LgBrandFeatureSeed(
        slug="jet-cool",
        title="Быстрое охлаждение",
        text="Режим быстрого охлаждения ускоряет выход помещения на комфортную температуру после запуска кондиционера.",
        icon="ac_unit",
        aliases=("Jet Cool", "Быстрое охлаждение"),
        keywords=("jet cool", "быстрое охлаждение", "охладить помещение"),
    ),
    LgBrandFeatureSeed(
        slug="smart-diagnosis",
        title="Умная диагностика",
        text="Smart Diagnosis помогает быстрее определить неисправность и упростить обслуживание оборудования.",
        icon="settings_suggest",
        aliases=("Smart Diagnosis", "Умная диагностика"),
        keywords=("smart diagnosis", "умная диагностика", "самодиагност"),
    ),
    LgBrandFeatureSeed(
        slug="artcool-design",
        title="ARTCOOL дизайн",
        text="Дизайнерские внутренние блоки ARTCOOL и Objet легче вписываются в интерьер, чем стандартные белые корпуса.",
        icon="auto_awesome",
        aliases=("ARTCOOL", "Objet", "Сменное изображение"),
        keywords=("artcool", "objet", "смены изображения", "ультратонкий дизайн", "стильный дизайн"),
    ),
    LgBrandFeatureSeed(
        slug="four-way-airflow",
        title="4-сторонний воздушный поток",
        text="Кассетные блоки распределяют воздух в четыре стороны, что полезно для офисов, залов и коммерческих помещений.",
        icon="waves",
        aliases=("4-way airflow", "Распределение воздуха в 4 стороны"),
        keywords=("4 стороны", "четыре стороны", "створк", "равномерное распределение воздуха"),
    ),
    LgBrandFeatureSeed(
        slug="drain-pump",
        title="Дренажный насос",
        text="Встроенный или опциональный дренажный насос упрощает отвод конденсата в коммерческих системах.",
        icon="water_drop",
        aliases=("Дренажный насос",),
        keywords=("дренажный насос",),
    ),
    LgBrandFeatureSeed(
        slug="zone-control",
        title="Зональное управление",
        text="Канальные системы могут обслуживать несколько зон или воздуховодов с отдельной логикой распределения воздуха.",
        icon="air",
        aliases=("Зональный контроллер", "Зональное управление"),
        keywords=("зональ", "9 воздуховод", "4-х помещ"),
    ),
)
