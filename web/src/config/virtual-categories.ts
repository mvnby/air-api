export type CatalogSort =
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
        sort?: CatalogSort;
    };
    indexable?: boolean;
}

export const VIRTUAL_CATEGORIES: VirtualCategoryConfig[] = [
    {
        slug: "inverter",
        seoTitle: "Купить инверторную сплит-систему в Витебске",
        seoDescription:
            "Инверторные кондиционеры в Витебске: тихие и энергоэффективные модели с установкой под ключ.",
        h1: "Инверторные кондиционеры в Витебске",
        intro: "Подбор инверторных сплит-систем с монтажом и гарантией в Витебске.",
        filters: {
            tag_slugs: ["inverter"],
            is_inverter: true,
            sort: "newest",
        },
        indexable: true,
    },
    {
        slug: "wifi",
        seoTitle: "Купить кондиционер с Wi-Fi в Витебске",
        seoDescription:
            "Кондиционеры с Wi-Fi управлением в Витебске: подбор моделей и установка под ключ.",
        h1: "Кондиционеры с Wi-Fi в Витебске",
        intro: "Подберем сплит-системы с управлением через приложение и голосовые ассистенты.",
        filters: {
            tag_slugs: ["wifi-builtin"],
            sort: "newest",
        },
        indexable: true,
    },
    {
        slug: "heating",
        seoTitle: "Купить кондиционер для обогрева зимой в Витебске",
        seoDescription:
            "Кондиционеры для обогрева в мороз в Витебске: модели с зимним режимом и установкой.",
        h1: "Кондиционеры для обогрева зимой в Витебске",
        intro: "Модели для межсезонья и зимней эксплуатации с профессиональным монтажом.",
        filters: {
            tag_slugs: ["winter-25", "winter-30"],
            sort: "newest",
        },
        indexable: true,
    },
    {
        slug: "silent",
        seoTitle: "Купить тихий кондиционер в Витебске",
        seoDescription:
            "Тихие кондиционеры в Витебске для спальни и детской: подбор, доставка и монтаж.",
        h1: "Тихие кондиционеры в Витебске",
        intro: "Подбор малошумных моделей для комфортного сна и работы.",
        filters: {
            tag_slugs: ["noise-silent"],
            sort: "newest",
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
            area_min: 30,
            area_max: 39,
            sort: "newest",
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
            area_min: 40,
            area_max: 59,
            sort: "newest",
        },
        indexable: true,
    },
    {
        slug: "do-70m2",
        seoTitle: "Купить кондиционер до 70 м² в Витебске",
        seoDescription:
            "Кондиционеры для помещений до 70 м² в Витебске: подбор производительных сплит-систем.",
        h1: "Кондиционеры до 70 м² в Витебске",
        intro: "Решения для просторных помещений и коммерческих зон до 70 м².",
        filters: {
            area_min: 60,
            area_max: 70,
            sort: "newest",
        },
        indexable: true,
    },
];

export function getVirtualCategoryBySlug(slug: string) {
    return VIRTUAL_CATEGORIES.find((item) => item.slug === slug);
}
