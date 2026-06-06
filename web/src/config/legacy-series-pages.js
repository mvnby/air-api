export const LEGACY_HAIER_SERIES_PAGES = [
    {
        slug: "haier-home",
        brandSlug: "haier",
        brandTitle: "Haier",
        seriesTitle: "Home",
        h1: "Кондиционеры Haier Home в Витебске",
        seoTitle: "Кондиционеры Haier Home: купить в Витебске",
        seoDescription:
            "Кондиционеры Haier Home в Витебске: подбор настенной сплит-системы, продажа, монтаж и сервис MVN.",
        intro:
            "Серия Haier Home подходит для спокойного базового охлаждения квартиры или небольшого офиса. Поможем сравнить актуальные модели Haier по мощности, шуму, наличию и условиям монтажа.",
    },
    {
        slug: "lightera",
        brandSlug: "haier",
        brandTitle: "Haier",
        seriesTitle: "Lightera",
        h1: "Кондиционеры Haier Lightera в Витебске",
        seoTitle: "Кондиционеры Haier Lightera: купить в Витебске",
        seoDescription:
            "Кондиционеры Haier Lightera в Витебске: подбор, продажа, монтаж и обслуживание климатической техники MVN.",
        intro:
            "Haier Lightera выбирают за тихую работу, комфортные режимы и удобное управление. Если нужной модели нет в наличии, подберем актуальную замену Haier по мощности и функциям.",
    },
];

export function getLegacyHaierSeriesPage(slug) {
    return LEGACY_HAIER_SERIES_PAGES.find((page) => page.slug === slug) || null;
}
