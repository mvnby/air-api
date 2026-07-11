export type ServiceGroupId = "setup" | "care" | "engineering";

export type ServiceId =
    | "preinstallation"
    | "installation"
    | "dismantling"
    | "maintenance"
    | "repair"
    | "vrf"
    | "server-room";

export interface ServiceDefinition {
    id: ServiceId;
    group: ServiceGroupId;
    title: string;
    description: string;
    cue: string;
    href: string;
    icon: string;
    image: string;
}

export interface ServiceGroup {
    id: ServiceGroupId;
    kicker: string;
    title: string;
    description: string;
    serviceIds: ServiceId[];
}

export const services: ServiceDefinition[] = [
    {
        id: "preinstallation",
        group: "setup",
        title: "Закладка коммуникаций",
        description:
            "Прокладываем трубы, дренаж и кабель до чистовой отделки, чтобы скрыть основную часть трассы. Схему определяем по планировке и отводу дренажа.",
        cue: "Ремонт ещё идёт",
        href: "/services/zakladka-kommunikaciy-kondicionera/",
        icon: "cable",
        image: "/img/services/v2/preinstallation.svg",
    },
    {
        id: "installation",
        group: "setup",
        title: "Монтаж кондиционеров",
        description:
            "Устанавливаем внутренний и наружный блок, вакуумируем трассу и запускаем систему по заранее согласованной схеме.",
        cue: "Нужна новая система",
        href: "/montaj-konditionerov/",
        icon: "construction",
        image: "/img/services/v2/installation.svg",
    },
    {
        id: "dismantling",
        group: "setup",
        title: "Демонтаж кондиционера",
        description:
            "Снимаем внутренний и наружный блок для замены или переноса. Хладагент сохраняем, если состояние системы это позволяет.",
        cue: "Переезд или замена",
        href: "/services/demontazh-kondicionera/",
        icon: "move_down",
        image: "/img/services/v2/dismantling.svg",
    },
    {
        id: "maintenance",
        group: "care",
        title: "Обслуживание кондиционеров",
        description:
            "Чистим фильтры, теплообменник, крыльчатку и дренаж, проверяем герметичность и рабочие параметры; давление — при необходимости.",
        cue: "Пахнет или слабо дует",
        href: "/obslujivanie-kondicionerov/",
        icon: "cleaning_services",
        image: "/img/services/v2/maintenance.svg",
    },
    {
        id: "repair",
        group: "care",
        title: "Ремонт кондиционеров",
        description:
            "Диагностируем, почему кондиционер не охлаждает, течёт, шумит или выдаёт ошибку. Стоимость называем после выявления причины.",
        cue: "Не охлаждает или течёт",
        href: "/services/repair/",
        icon: "engineering",
        image: "/img/services/v2/repair.svg",
    },
    {
        id: "vrf",
        group: "engineering",
        title: "VRF и мультизональные системы",
        description:
            "Проектируем системы для множества зон, длинных трасс и централизованного управления. VRF дороже сплит-систем и выбирается под задачу объекта.",
        cue: "Много зон и длинные трассы",
        href: "/services/vrf-sistemy/",
        icon: "settings_ethernet",
        image: "/img/services/v2/vrf.svg",
    },
    {
        id: "server-room",
        group: "engineering",
        title: "Серверные и технические помещения",
        description:
            "Подбираем систему для работы 24/7 и охлаждения зимой; при необходимости предусматриваем резервный блок, автоматику переключения и контроль температуры.",
        cue: "Оборудование работает 24/7",
        href: "/services/kondicionery-dlya-servernoy/",
        icon: "dns",
        image: "/img/services/v2/server-room.svg",
    },
];

export const serviceGroups: ServiceGroup[] = [
    {
        id: "setup",
        kicker: "Квартира, дом или небольшой объект",
        title: "Подготовить, установить или снять",
        description:
            "От скрытой трассы во время ремонта до монтажа новой системы или снятия кондиционера для переноса и замены.",
        serviceIds: ["preinstallation", "installation", "dismantling"],
    },
    {
        id: "care",
        kicker: "Система уже установлена",
        title: "Почистить или отремонтировать",
        description:
            "Разделяем профилактическую чистку и поиск неисправности: это разные задачи, состав работ и порядок оценки.",
        serviceIds: ["maintenance", "repair"],
    },
    {
        id: "engineering",
        kicker: "Коммерческие и технические объекты",
        title: "Спроектировать систему для объекта",
        description:
            "Учитываем количество зон, тепловыделения, длины трасс, режим работы, резерв и требования к управлению.",
        serviceIds: ["vrf", "server-room"],
    },
];

const servicesById = new Map(services.map((service) => [service.id, service]));

export const getServicesByIds = (ids: ServiceId[]): ServiceDefinition[] =>
    ids.map((id) => servicesById.get(id)).filter(Boolean) as ServiceDefinition[];
