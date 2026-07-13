export type HomeSelectionRooms = "single" | "multiple";
export type HomeSelectionPriority = "price" | "silent" | "heating" | "wifi";

export interface HomeSelectionAnswers {
    rooms: HomeSelectionRooms;
    area: 20 | 25 | 35 | 50 | 70;
    priority: HomeSelectionPriority;
    inverter: boolean;
}

export interface HomeSelectionResult {
    href: string;
    title: string;
    summary: string;
    criteria: string[];
}

const priorityCriteria: Record<HomeSelectionPriority, string> = {
    price: "Сначала доступные по цене",
    silent: "Тихая работа для спальни или детской",
    heating: "Обогрев при температуре до −20 °C",
    wifi: "Управление по Wi-Fi",
};

export function buildHomeSelectionResult(
    answers: HomeSelectionAnswers,
): HomeSelectionResult {
    if (answers.rooms === "multiple") {
        return {
            href: "/catalog/multi-split/",
            title: "Мультисплит для нескольких комнат",
            summary:
                "Покажем системы с одним наружным блоком. Мощность внутренних блоков и схему трасс мастер уточнит по каждой комнате.",
            criteria: [
                "Несколько помещений",
                `Ориентир по площади: до ${answers.area} м²`,
                `${priorityCriteria[answers.priority]} — уточнить по внутренним блокам`,
            ],
        };
    }

    const params = new URLSearchParams();
    params.set("area_max", String(answers.area));

    if (answers.priority === "price") {
        params.set("sort", "price_asc");
    }
    if (answers.priority === "silent") {
        params.set("tag_slugs", "noise-silent");
    }
    if (answers.priority === "heating") {
        params.set("heating_min", "-20");
    }
    if (answers.priority === "wifi") {
        params.set("has_wifi", "true");
    }
    if (answers.inverter) {
        params.set("is_inverter", "true");
    }

    return {
        href: `/catalog/?${params.toString()}`,
        title: `Модели для помещения до ${answers.area} м²`,
        summary:
            "Каталог уже отфильтрован по вашим ответам. Перед покупкой проверьте теплопритоки, высоту потолка и место установки.",
        criteria: [
            `Одно помещение до ${answers.area} м²`,
            priorityCriteria[answers.priority],
            answers.inverter ? "Инверторный компрессор" : "Любой тип компрессора",
        ],
    };
}
