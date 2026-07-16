import type {
    CatalogSort,
    VirtualCategoryConfig,
} from "../config/virtual-categories";
import { VIRTUAL_CATEGORIES } from "../config/virtual-categories";

export interface CatalogQuery {
    page?: number | string;
    limit?: number | string;
    sort?: CatalogSort;
    tag_slugs?: string[];
    is_inverter?: boolean;
    has_wifi?: boolean;
    color?: "black";
    heating_min?: number;
    area_min?: number;
    area_max?: number;
}

interface NormalizedFilters {
    sort: CatalogSort;
    tag_slugs: string[];
    is_inverter?: boolean;
    has_wifi?: boolean;
    color?: "black";
    heating_min?: number;
    area_min?: number;
    area_max?: number;
}

const DEFAULT_SORT: CatalogSort = "recommended";
const TECHNICAL_DEFAULT_TAGS = new Set<string>(["cat-household"]);

function normalizeTags(tags: string[] = []): string[] {
    const clean = tags
        .map((tag) => tag.trim().toLowerCase())
        .filter(Boolean)
        .filter((tag) => !TECHNICAL_DEFAULT_TAGS.has(tag));

    return [...new Set(clean)].sort();
}

function normalizeNumber(value: unknown): number | undefined {
    if (typeof value === "number" && Number.isFinite(value)) {
        return value;
    }
    if (typeof value === "string" && value.trim()) {
        const parsed = Number.parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : undefined;
    }
    return undefined;
}

function normalizeFilters(filters: CatalogQuery): NormalizedFilters {
    return {
        sort: filters.sort || DEFAULT_SORT,
        tag_slugs: normalizeTags(filters.tag_slugs || []),
        is_inverter:
            typeof filters.is_inverter === "boolean"
                ? filters.is_inverter
                : undefined,
        has_wifi:
            typeof filters.has_wifi === "boolean"
                ? filters.has_wifi
                : undefined,
        color: filters.color === "black" ? "black" : undefined,
        heating_min: normalizeNumber(filters.heating_min),
        area_min: normalizeNumber(filters.area_min),
        area_max: normalizeNumber(filters.area_max),
    };
}

function areFiltersEqual(left: NormalizedFilters, right: NormalizedFilters) {
    return (
        left.sort === right.sort &&
        left.is_inverter === right.is_inverter &&
        left.has_wifi === right.has_wifi &&
        left.color === right.color &&
        left.heating_min === right.heating_min &&
        left.area_min === right.area_min &&
        left.area_max === right.area_max &&
        left.tag_slugs.length === right.tag_slugs.length &&
        left.tag_slugs.every((tag, idx) => tag === right.tag_slugs[idx])
    );
}

export function buildCatalogQueryFromVirtual(
    config: VirtualCategoryConfig,
): CatalogQuery {
    return {
        page: 1,
        limit: 20,
        sort: config.filters.sort || DEFAULT_SORT,
        tag_slugs: [...(config.filters.tag_slugs || [])],
        is_inverter: config.filters.is_inverter,
        has_wifi: config.filters.has_wifi,
        color: config.filters.color,
        heating_min: config.filters.heating_min,
        area_min: config.filters.area_min,
        area_max: config.filters.area_max,
    };
}

export function matchVirtualCategoryByFilters(
    filters: CatalogQuery,
): VirtualCategoryConfig | null {
    const normalizedInput = normalizeFilters(filters);

    for (const category of VIRTUAL_CATEGORIES) {
        const normalizedCategory = normalizeFilters({
            sort: category.filters.sort || DEFAULT_SORT,
            tag_slugs: category.filters.tag_slugs || [],
            is_inverter: category.filters.is_inverter,
            has_wifi: category.filters.has_wifi,
            color: category.filters.color,
            heating_min: category.filters.heating_min,
            area_min: category.filters.area_min,
            area_max: category.filters.area_max,
        });
        if (areFiltersEqual(normalizedInput, normalizedCategory)) {
            return category;
        }
    }

    return null;
}
