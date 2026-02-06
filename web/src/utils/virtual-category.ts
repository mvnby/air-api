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
    area_min?: number;
    area_max?: number;
}

interface NormalizedFilters {
    sort: CatalogSort;
    tag_slugs: string[];
    is_inverter?: boolean;
    area_min?: number;
    area_max?: number;
}

const DEFAULT_SORT: CatalogSort = "newest";
const TECHNICAL_DEFAULT_TAGS = new Set(["wall"]);

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
        area_min: normalizeNumber(filters.area_min),
        area_max: normalizeNumber(filters.area_max),
    };
}

function areFiltersEqual(left: NormalizedFilters, right: NormalizedFilters) {
    return (
        left.sort === right.sort &&
        left.is_inverter === right.is_inverter &&
        left.area_min === right.area_min &&
        left.area_max === right.area_max &&
        left.tag_slugs.length === right.tag_slugs.length &&
        left.tag_slugs.every((tag, idx) => tag === right.tag_slugs[idx])
    );
}

export function buildCatalogQueryFromVirtual(
    config: VirtualCategoryConfig,
): CatalogQuery {
    const tags = [...(config.filters.tag_slugs || [])];
    if (!tags.includes("wall")) {
        tags.push("wall");
    }

    return {
        page: 1,
        limit: 100,
        sort: config.filters.sort || DEFAULT_SORT,
        tag_slugs: tags,
        is_inverter: config.filters.is_inverter,
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
            area_min: category.filters.area_min,
            area_max: category.filters.area_max,
        });
        if (areFiltersEqual(normalizedInput, normalizedCategory)) {
            return category;
        }
    }

    return null;
}
