type AvailabilityInput = {
    vitebsk_qty?: number | string | null;
    minsk_qty?: number | string | null;
    availability_status?: string | null;
    vitebskQty?: number | string | null;
    minskQty?: number | string | null;
    availabilityStatus?: string | null;
};

export type ProductAvailabilityDisplay = {
    message: string;
    tone: "vitebsk" | "minsk" | "available" | "unknown" | "out";
    isPurchasable: boolean;
    canOrder: boolean;
    isUnknown: boolean;
    isOutOfStock: boolean;
    isExplicitOutOfStock: boolean;
};

const toQty = (value: number | string | null | undefined) => Number(value || 0);

export const hasKnownProductPrice = (price: number | string | null | undefined) => {
    const numeric = Number(price);
    return Number.isFinite(numeric) && numeric > 0;
};

export const formatProductPrice = (
    price: number | string | null | undefined,
    options: { fallback?: string; locale?: string } = {},
) => {
    if (!hasKnownProductPrice(price)) {
        return options.fallback || "Цену уточняйте";
    }
    return Number(price).toLocaleString(options.locale || "ru-RU");
};

export const getProductAvailabilityDisplay = (
    product: AvailabilityInput,
): ProductAvailabilityDisplay => {
    const vitebskQty = toQty(product.vitebsk_qty ?? product.vitebskQty);
    const minskQty = toQty(product.minsk_qty ?? product.minskQty);
    const status = String(product.availability_status ?? product.availabilityStatus ?? "").trim().toLowerCase();

    if (vitebskQty > 0) {
        return {
            message: "В наличии в Витебске",
            tone: "vitebsk",
            isPurchasable: true,
            canOrder: true,
            isUnknown: false,
            isOutOfStock: false,
            isExplicitOutOfStock: false,
        };
    }
    if (minskQty > 0) {
        return {
            message: "В наличии в Минске",
            tone: "minsk",
            isPurchasable: true,
            canOrder: true,
            isUnknown: false,
            isOutOfStock: false,
            isExplicitOutOfStock: false,
        };
    }
    if (status === "in_stock_now") {
        return {
            message: "В наличии",
            tone: "available",
            isPurchasable: true,
            canOrder: true,
            isUnknown: false,
            isOutOfStock: false,
            isExplicitOutOfStock: false,
        };
    }
    if (status === "available_2_3_days") {
        return {
            message: "В наличии в Минске, срок поставки 2-4 дня",
            tone: "minsk",
            isPurchasable: true,
            canOrder: true,
            isUnknown: false,
            isOutOfStock: false,
            isExplicitOutOfStock: false,
        };
    }
    if (status === "out_of_stock") {
        return {
            message: "Нет в наличии",
            tone: "out",
            isPurchasable: false,
            canOrder: false,
            isUnknown: false,
            isOutOfStock: true,
            isExplicitOutOfStock: true,
        };
    }
    return {
        message: "Наличие уточняйте",
        tone: "unknown",
        isPurchasable: false,
        canOrder: false,
        isUnknown: true,
        isOutOfStock: false,
        isExplicitOutOfStock: false,
    };
};

export const resolveProductAvailability = getProductAvailabilityDisplay;
