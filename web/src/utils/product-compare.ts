export const PRODUCT_COMPARE_STORAGE_KEY = "mvn:product-compare";
export const MAX_COMPARE_PRODUCTS = 3;

export interface ProductCompareItem {
    slug: string;
    title: string;
    snapshot?: ProductCompareSnapshot;
}

export interface ProductCompareSnapshot {
    slug: string;
    title: string;
    price: number | null;
    area: number | null;
    card_image: string;
    main_image: string;
    is_inverter: boolean | null;
    vitebsk_qty: number;
    minsk_qty: number;
    availability_status: string;
    specs: Record<string, string | number | boolean>;
}

const COMPARE_SPEC_KEYS = [
    "compressor_type_norm",
    "wifi_ready",
    "wifi",
    "min_temp_heat",
    "temp_range_heat",
    "noise_indoor_min",
    "indoor_noise",
    "noise_level",
] as const;

const normalizeText = (value: unknown, maxLength: number) =>
    String(value || "").trim().slice(0, maxLength);

const normalizeNumber = (value: unknown): number | null => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
};

export function buildProductCompareSnapshot(
    value: Record<string, any>,
): ProductCompareSnapshot {
    const specs: Record<string, string | number | boolean> = {};
    for (const key of COMPARE_SPEC_KEYS) {
        const raw = value?.specs?.[key];
        if (["string", "number", "boolean"].includes(typeof raw)) {
            specs[key] = typeof raw === "string" ? raw.slice(0, 120) : raw;
        }
    }

    return {
        slug: normalizeText(value?.slug, 180),
        title: normalizeText(value?.title, 240),
        price: normalizeNumber(value?.price),
        area: normalizeNumber(value?.area),
        card_image: normalizeText(value?.card_image, 600),
        main_image: normalizeText(value?.main_image, 600),
        is_inverter:
            typeof value?.is_inverter === "boolean" ? value.is_inverter : null,
        vitebsk_qty: normalizeNumber(value?.vitebsk_qty) || 0,
        minsk_qty: normalizeNumber(value?.minsk_qty) || 0,
        availability_status: normalizeText(value?.availability_status, 80),
        specs,
    };
}

export function normalizeCompareItems(value: unknown): ProductCompareItem[] {
    if (!Array.isArray(value)) return [];

    const seen = new Set<string>();
    const items: ProductCompareItem[] = [];

    for (const raw of value) {
        if (!raw || typeof raw !== "object") continue;
        const candidate = raw as Record<string, unknown>;
        const slug = normalizeText(candidate.slug, 180);
        const title = normalizeText(candidate.title, 240);
        if (!slug || !/^[a-z0-9_-]+$/i.test(slug) || seen.has(slug)) continue;

        seen.add(slug);
        const snapshotSource = candidate.snapshot;
        const normalizedSnapshot =
            snapshotSource && typeof snapshotSource === "object"
                ? buildProductCompareSnapshot(snapshotSource as Record<string, any>)
                : undefined;
        const snapshot = normalizedSnapshot
            ? { ...normalizedSnapshot, slug, title: title || slug }
            : undefined;
        items.push({
            slug,
            title: title || slug,
            ...(snapshot?.slug ? { snapshot } : {}),
        });
        if (items.length >= MAX_COMPARE_PRODUCTS) break;
    }

    return items;
}

export function buildCompareUrl(items: ProductCompareItem[]): string {
    const slugs = normalizeCompareItems(items).map((item) => item.slug);
    if (slugs.length === 0) return "/compare/";
    return `/compare/?products=${encodeURIComponent(slugs.join(","))}`;
}

export function readCompareSlugsFromSearch(search: string): string[] {
    const raw = new URLSearchParams(search).get("products") || "";
    return [
        ...new Set(
            raw
                .split(",")
                .map((slug) => slug.trim())
                .filter((slug) => /^[a-z0-9_-]+$/i.test(slug)),
        ),
    ].slice(0, MAX_COMPARE_PRODUCTS);
}
