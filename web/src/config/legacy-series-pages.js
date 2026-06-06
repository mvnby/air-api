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
            "Линейка Haier Home из старого каталога сохранена как чистая canonical-страница. Перед заказом уточним актуальные модели Haier, наличие и условия монтажа.",
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
            "Страница Haier Lightera закрывает старый адрес серии и ведет покупателей к актуальному ассортименту Haier. Поможем подобрать замену по мощности, шуму и функциям.",
    },
];

export function getLegacyHaierSeriesPage(slug) {
    return LEGACY_HAIER_SERIES_PAGES.find((page) => page.slug === slug) || null;
}
