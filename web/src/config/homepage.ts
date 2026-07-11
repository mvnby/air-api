export interface HomepageIntent {
    title: string;
    description: string;
    details: string[];
    cta: string;
    href: string;
    icon: string;
    analyticsItem: string;
}

export interface HomepageQuickPick {
    title: string;
    note: string;
    href: string;
    icon: string;
    analyticsItem: string;
}

export const HOMEPAGE_INTENTS: HomepageIntent[] = [
    {
        title: "Подобрать и купить",
        description: "Кондиционер под помещение, режим работы и бюджет.",
        details: ["для спальни и гостиной", "для обогрева", "в наличии в Витебске"],
        cta: "Подобрать модели",
        href: "/catalog/",
        icon: "tune",
        analyticsItem: "buy",
    },
    {
        title: "Установить свой кондиционер",
        description: "Монтаж нового или б/у оборудования, даже если оно куплено не у нас.",
        details: ["трасса и блоки", "пылеудаление", "вакуумирование и запуск"],
        cta: "Рассчитать монтаж",
        href: "/montaj-konditionerov/#installation-request",
        icon: "construction",
        analyticsItem: "installation",
    },
    {
        title: "Сервис и ремонт",
        description: "Плановая чистка или диагностика, когда кондиционер уже работает неправильно.",
        details: ["чистка и дезинфекция", "дренаж и протечки", "ошибки, шум и слабое охлаждение"],
        cta: "Выбрать услугу",
        href: "/services/",
        icon: "home_repair_service",
        analyticsItem: "service",
    },
    {
        title: "Для бизнеса и объектов",
        description: "Решения для нескольких помещений и объектов с постоянной тепловой нагрузкой.",
        details: ["офисы и магазины", "серверные", "склады и производства"],
        cta: "Получить решение для объекта",
        href: "#business-solutions",
        icon: "domain",
        analyticsItem: "business",
    },
];

export const HOMEPAGE_QUICK_PICKS: HomepageQuickPick[] = [
    {
        title: "До 25 м²",
        note: "Спальня или небольшая комната",
        href: "/catalog/do-25m2/",
        icon: "bedroom_parent",
        analyticsItem: "area_25",
    },
    {
        title: "Тихие",
        note: "Для спальни и детской",
        href: "/catalog/silent/",
        icon: "volume_off",
        analyticsItem: "silent",
    },
    {
        title: "Для обогрева",
        note: "Модели для мороза",
        href: "/catalog/heating/",
        icon: "mode_heat",
        analyticsItem: "heating",
    },
    {
        title: "С Wi-Fi",
        note: "Управление через приложение",
        href: "/catalog/wifi/",
        icon: "wifi",
        analyticsItem: "wifi",
    },
    {
        title: "Для 2–3 комнат",
        note: "Мультисплит-системы",
        href: "/catalog/multi-split/",
        icon: "account_tree",
        analyticsItem: "multi_split",
    },
    {
        title: "До 35 м²",
        note: "Гостиная или небольшой офис",
        href: "/catalog/do-35m2/",
        icon: "meeting_room",
        analyticsItem: "area_35",
    },
];

export const HOMEPAGE_ANALYTICS_EVENTS = {
    heroSelect: "home_hero_select_click",
    heroInstallation: "home_hero_installation_click",
    intent: "home_intent_click",
    quickPick: "home_quick_pick_click",
    productFit: "home_product_fit_click",
    mobileAction: "home_mobile_action_click",
    selectorComplete: "home_selector_complete",
} as const;
