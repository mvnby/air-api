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
];

export function getVirtualCategoryBySlug(slug: string) {
    return VIRTUAL_CATEGORIES.find((item) => item.slug === slug);
}
