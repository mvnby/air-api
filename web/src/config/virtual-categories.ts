export type CatalogSort =
    | "recommended"
    | "newest"
    | "price_asc"
    | "price_desc"
    | "area_asc"
    | "area_desc";

export interface VirtualCategoryConfig {
    slug: string;
    seoTitle: string;
    seoDescription: string;
    h1: string;
    intro?: string;
    filters: {
        tag_slugs?: string[];
        area_min?: number;
        area_max?: number;
        is_inverter?: boolean;
        has_wifi?: boolean;
        heating_min?: number;
        sort?: CatalogSort;
    };
    indexable?: boolean;
}

export const VIRTUAL_CATEGORIES: VirtualCategoryConfig[] = [
    {
        slug: "inverter",
        seoTitle: "Купить инверторную сплит-систему в Витебске",
        seoDescription:
            "Инверторные кондиционеры в Витебске: тихие и энергоэффективные модели с подбором и монтажом.",
        h1: "Инверторные кондиционеры в Витебске",
        intro: "Поможем выбрать инверторную сплит-систему под площадь комнаты и режим использования в Витебске.",
        filters: {
            tag_slugs: ["cat-household"],
            is_inverter: true,
            sort: "recommended",
        },
        indexable: true,
    },
    {
        slug: "wifi",
        seoTitle: "Купить кондиционер с Wi-Fi в Витебске",
        seoDescription:
            "Кондиционеры с Wi-Fi управлением в Витебске: подбор моделей, доставка и установка.",
        h1: "Кондиционеры с Wi-Fi в Витебске",
        intro: "Подберем сплит-системы с управлением через приложение и голосовые ассистенты.",
        filters: {
            tag_slugs: ["cat-household"],
            has_wifi: true,
            sort: "recommended",
        },
        indexable: true,
    },
    {
        slug: "heating",
        seoTitle: "Купить кондиционер для обогрева зимой в Витебске",
        seoDescription:
            "Кондиционеры для обогрева в мороз в Витебске: модели с зимним режимом и установкой.",
        h1: "Кондиционеры для обогрева зимой в Витебске",
        intro: "Модели для межсезонья и зимы: учитываем минимальную температуру обогрева и место установки наружного блока.",
        filters: {
            tag_slugs: ["cat-household"],
            heating_min: -20,
            sort: "recommended",
        },
        indexable: true,
    },
    {
        slug: "silent",
        seoTitle: "Купить тихий кондиционер в Витебске",
        seoDescription:
            "Тихие кондиционеры в Витебске для спальни и детской: подбор, доставка и монтаж.",
        h1: "Тихие кондиционеры в Витебске",
        intro: "Подбор малошумных моделей для спальни, детской и рабочего кабинета.",
        filters: {
            tag_slugs: ["cat-household", "noise-silent"],
            sort: "recommended",
        },
        indexable: true,
    },
    {
        slug: "do-25m2",
        seoTitle: "Купить кондиционер до 25 м² в Витебске",
        seoDescription:
            "Кондиционеры для комнат до 25 м² в Витебске: модели для спальни, детской и небольшой гостиной.",
        h1: "Кондиционеры до 25 м² в Витебске",
        intro: "Компактные сплит-системы для спальни, детской или небольшой гостиной с монтажом в Витебске.",
        filters: {
            tag_slugs: ["cat-household"],
            area_max: 25,
            sort: "recommended",
        },
        indexable: true,
    },
    {
        slug: "do-35m2",
        seoTitle: "Купить кондиционер до 35 м² в Витебске",
        seoDescription:
            "Кондиционеры для помещений до 35 м² в Витебске: оптимальные модели по мощности и цене.",
        h1: "Кондиционеры до 35 м² в Витебске",
        intro: "Подбор сплит-систем для квартир, спален и небольших офисов до 35 м².",
        filters: {
            tag_slugs: ["cat-household"],
            area_max: 35,
            sort: "recommended",
        },
        indexable: true,
    },
    {
        slug: "do-50m2",
        seoTitle: "Купить кондиционер до 50 м² в Витебске",
        seoDescription:
            "Кондиционеры для помещений до 50 м² в Витебске: мощные и энергоэффективные модели.",
        h1: "Кондиционеры до 50 м² в Витебске",
        intro: "Подбор кондиционеров для гостиных, студий и офисов площадью до 50 м².",
        filters: {
            tag_slugs: ["cat-household"],
            area_max: 50,
            sort: "recommended",
        },
        indexable: true,
    },
    {
        slug: "do-70m2",
        seoTitle: "Купить кондиционер до 70 м² в Витебске",
        seoDescription:
            "Кондиционеры для помещений до 70 м² в Витебске: подбор производительных сплит-систем.",
        h1: "Кондиционеры до 70 м² в Витебске",
        intro: "Производительные модели для больших комнат, студий, офисов и торговых помещений до 70 м².",
        filters: {
            tag_slugs: ["cat-household"],
            area_max: 70,
            sort: "recommended",
        },
        indexable: true,
    },
];

export function getVirtualCategoryBySlug(slug: string) {
    return VIRTUAL_CATEGORIES.find((item) => item.slug === slug);
}
