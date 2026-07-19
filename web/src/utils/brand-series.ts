export interface BrandSeriesProduct {
    title: string;
    slug?: string;
    specs?: Record<string, unknown>;
    series?: {
        title?: string | null;
        slug?: string | null;
        tagline?: string | null;
        short_description?: string | null;
        description?: string | null;
        hero_image?: string | null;
        gallery_images?: string[] | null;
        features?: string[] | null;
        brand_features?: Array<{
            id?: number | null;
            title?: string | null;
            slug?: string | null;
            text?: string | null;
            image_url?: string | null;
            icon?: string | null;
            footnote?: string | null;
            source_url?: string | null;
            sort_order?: number | null;
        }> | null;
        feature_blocks?: Array<{
            title?: string | null;
            text?: string | null;
            image_url?: string | null;
            icon?: string | null;
            footnote?: string | null;
        }> | null;
        content_blocks?: Array<{
            kind?: string | null;
            title?: string | null;
            text?: string | null;
            image_url?: string | null;
            layout?: string | null;
        }> | null;
        footnotes?: string[] | null;
    } | null;
    tags?: Array<{
        title?: string;
        slug?: string;
        is_public?: boolean;
        sort_order?: number;
        group?: {
            slug: string;
            is_public: boolean;
        };
    }>;
}

export interface BrandSeriesFeatureBlock {
    title: string;
    text: string;
    imageUrl: string;
    icon: string;
    footnote: string;
}

export interface BrandSeriesBrandFeature extends BrandSeriesFeatureBlock {
    id: number | null;
    slug: string;
    sourceUrl: string;
    sortOrder: number;
}

export interface BrandSeriesContentBlock {
    kind: string;
    title: string;
    text: string;
    imageUrl: string;
    layout: string;
}

export interface BrandSeriesVisualBlock extends BrandSeriesFeatureBlock {
    source: "feature_block" | "brand_feature" | "content_block";
}

const CATALOG_GROUP_DEFINITIONS = {
    household: {
        key: "household",
        navTitle: "Бытовые серии",
        shortLabel: "настенные",
        emptyTitle: "Бытовые модели без серии",
        order: 10,
    },
    mobile: {
        key: "mobile",
        navTitle: "Мобильные",
        shortLabel: "мобильные",
        emptyTitle: "Мобильные модели без серии",
        order: 20,
    },
    multi: {
        key: "multi",
        navTitle: "Мульти-сплит",
        shortLabel: "мульти-сплит",
        emptyTitle: "Мульти-сплит без серии",
        order: 30,
    },
    industrial: {
        key: "industrial",
        navTitle: "Полупром",
        shortLabel: "полупром",
        emptyTitle: "Полупромышленные модели без серии",
        order: 40,
    },
    other: {
        key: "other",
        navTitle: "Другие",
        shortLabel: "другие",
        emptyTitle: "Другие модели",
        order: 50,
    },
} as const;

export type CatalogGroupKey = keyof typeof CATALOG_GROUP_DEFINITIONS;

export interface BrandCatalogGroup {
    key: CatalogGroupKey;
    title: string;
    navTitle: string;
    shortLabel: string;
    emptyTitle: string;
    order: number;
}

export interface BrandSeriesGroup<T extends BrandSeriesProduct> {
    key: string;
    title: string;
    tagline: string;
    shortDescription: string;
    description: string;
    heroImage: string;
    galleryImages: string[];
    features: string[];
    brandFeatures: BrandSeriesBrandFeature[];
    featureBlocks: BrandSeriesFeatureBlock[];
    contentBlocks: BrandSeriesContentBlock[];
    footnotes: string[];
    primaryImage: string;
    visualFeatureBlocks: BrandSeriesVisualBlock[];
    catalogGroupKey: CatalogGroupKey;
    products: T[];
    anchorId: string;
    catalogGroup: BrandCatalogGroup;
    displayTitle: string;
    distinctFeatures: string[];
    previewProducts: T[];
}

export interface BrandCatalogSeriesGroup<T extends BrandSeriesProduct> extends BrandCatalogGroup {
    series: BrandSeriesGroup<T>[];
}

export interface BrandProductsWithoutSeriesGroup<T extends BrandSeriesProduct> extends BrandCatalogGroup {
    products: T[];
}

export interface BrandSeriesCatalog<T extends BrandSeriesProduct> {
    seriesSourceProducts: T[];
    seriesGroups: BrandSeriesGroup<T>[];
    seriesGroupsByCatalog: BrandCatalogSeriesGroup<T>[];
    productsWithoutSeriesByCatalog: BrandProductsWithoutSeriesGroup<T>[];
}

const getCatalogGroups = (brandTitle: string): Record<CatalogGroupKey, BrandCatalogGroup> => ({
    household: {
        ...CATALOG_GROUP_DEFINITIONS.household,
        title: `Бытовые настенные кондиционеры ${brandTitle}`,
    },
    mobile: {
        ...CATALOG_GROUP_DEFINITIONS.mobile,
        title: `Мобильные кондиционеры ${brandTitle}`,
    },
    multi: {
        ...CATALOG_GROUP_DEFINITIONS.multi,
        title: `Мульти-сплит ${brandTitle}`,
    },
    industrial: {
        ...CATALOG_GROUP_DEFINITIONS.industrial,
        title: `Полупромышленные кондиционеры ${brandTitle}`,
    },
    other: {
        ...CATALOG_GROUP_DEFINITIONS.other,
        title: `Другие модели ${brandTitle}`,
    },
});

const asText = (value: unknown) => String(value || "").trim();

const normalizeText = (value: unknown) => asText(value).toLowerCase().replace(/ё/g, "е");

const slugifySeriesFallback = (value: string) =>
    value
        .toLowerCase()
        .replace(/ё/g, "е")
        .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
        .replace(/^-+|-+$/g, "");

const getProductSeriesTitle = (product: BrandSeriesProduct) =>
    asText(product.series?.title) || asText(product.specs?.series);

const normalizeSeriesFeatures = (value: unknown) =>
    Array.isArray(value)
        ? value.map((item) => asText(item)).filter(Boolean)
        : [];

const normalizeSeriesGalleryImages = (series: BrandSeriesProduct["series"]) => {
    const images = [
        asText(series?.hero_image),
        ...(Array.isArray(series?.gallery_images) ? series.gallery_images.map((item) => asText(item)) : []),
    ].filter(Boolean);
    return [...new Set(images)];
};

const normalizeSeriesFeatureBlocks = (value: unknown): BrandSeriesFeatureBlock[] =>
    Array.isArray(value)
        ? value
            .map((item) => {
                if (!item || typeof item !== "object") return null;
                const block = item as Record<string, unknown>;
                const title = asText(block.title);
                if (!title) return null;
                return {
                    title,
                    text: asText(block.text),
                    imageUrl: asText(block.image_url),
                    icon: asText(block.icon),
                    footnote: asText(block.footnote),
                };
            })
            .filter((item): item is BrandSeriesFeatureBlock => Boolean(item))
        : [];

const normalizeSeriesBrandFeatures = (value: unknown): BrandSeriesBrandFeature[] =>
    Array.isArray(value)
        ? value
            .map((item) => {
                if (!item || typeof item !== "object") return null;
                const feature = item as Record<string, unknown>;
                const title = asText(feature.title);
                if (!title) return null;
                const sortOrder = Number(feature.sort_order);
                return {
                    id: typeof feature.id === "number" ? feature.id : null,
                    title,
                    slug: asText(feature.slug),
                    text: asText(feature.text),
                    imageUrl: asText(feature.image_url),
                    icon: asText(feature.icon),
                    footnote: asText(feature.footnote),
                    sourceUrl: asText(feature.source_url),
                    sortOrder: Number.isFinite(sortOrder) ? sortOrder : 0,
                };
            })
            .filter((item): item is BrandSeriesBrandFeature => Boolean(item))
            .sort((a, b) => a.sortOrder - b.sortOrder || a.title.localeCompare(b.title, "ru"))
        : [];

const normalizeSeriesContentBlocks = (value: unknown): BrandSeriesContentBlock[] =>
    Array.isArray(value)
        ? value
            .map((item) => {
                if (!item || typeof item !== "object") return null;
                const block = item as Record<string, unknown>;
                const title = asText(block.title);
                const text = asText(block.text);
                const imageUrl = asText(block.image_url);
                if (!title && !text && !imageUrl) return null;
                return {
                    kind: asText(block.kind) || "text",
                    title,
                    text,
                    imageUrl,
                    layout: asText(block.layout) || "text_left",
                };
            })
            .filter((item): item is BrandSeriesContentBlock => Boolean(item))
        : [];

const getPrimarySeriesImage = (group: {
    galleryImages: string[];
    featureBlocks: BrandSeriesFeatureBlock[];
    brandFeatures: BrandSeriesBrandFeature[];
    contentBlocks: BrandSeriesContentBlock[];
}) =>
    group.galleryImages[0]
    || group.featureBlocks.find((block) => block.imageUrl)?.imageUrl
    || group.brandFeatures.find((block) => block.imageUrl)?.imageUrl
    || group.contentBlocks.find((block) => block.imageUrl)?.imageUrl
    || "";

const buildVisualFeatureBlocks = (group: {
    featureBlocks: BrandSeriesFeatureBlock[];
    brandFeatures: BrandSeriesBrandFeature[];
    contentBlocks: BrandSeriesContentBlock[];
}): BrandSeriesVisualBlock[] => {
    const seen = new Set<string>();
    const blocks: BrandSeriesVisualBlock[] = [];
    const addBlock = (block: BrandSeriesFeatureBlock, source: BrandSeriesVisualBlock["source"]) => {
        const key = normalizeText(`${block.title} ${block.text}`);
        if (!block.title || seen.has(key)) return;
        seen.add(key);
        blocks.push({ ...block, source });
    };

    group.featureBlocks.forEach((block) => addBlock(block, "feature_block"));
    group.brandFeatures.forEach((block) => addBlock(block, "brand_feature"));
    group.contentBlocks.forEach((block) =>
        addBlock(
            {
                title: block.title || "Особенность серии",
                text: block.text,
                imageUrl: block.imageUrl,
                icon: "",
                footnote: "",
            },
            "content_block",
        ),
    );

    return blocks;
};

const getTagSlugs = (product: BrandSeriesProduct) =>
    (product.tags || []).map((tag) => normalizeText(tag.slug || tag.title));

const hasTagSlug = (product: BrandSeriesProduct, slug: string) => getTagSlugs(product).includes(slug);

const getSpecValue = (product: BrandSeriesProduct, keys: string[]) => {
    const specs = product.specs || {};
    for (const key of keys) {
        const value = specs[key];
        if (value !== undefined && value !== null && String(value).trim() !== "") {
            return value;
        }
    }
    return "";
};

const parseSpecNumber = (value: unknown) => {
    if (value === null || value === undefined || value === "") return null;
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    const match = String(value).replace(",", ".").match(/[-+]?\d+(?:\.\d+)?/);
    if (!match) return null;
    const parsed = Number.parseFloat(match[0]);
    return Number.isFinite(parsed) ? parsed : null;
};

const formatDecimal = (value: number) =>
    value.toLocaleString("ru-RU", {
        maximumFractionDigits: 1,
    });

const normalizeCapacityToken = (value: unknown) => {
    const text = asText(value);
    const match = text.match(/\b(07|09|12|18|24|30|36|42|48|60)\b/);
    return match?.[1] || "";
};

const formatProductPowerLabel = (product: BrandSeriesProduct) => {
    const rawArea = product.specs?.area_m2;
    const area = parseSpecNumber(rawArea);
    if (area && area > 0) return `до ${formatDecimal(area)} м²`;

    const capacityClass = normalizeCapacityToken(
        getSpecValue(product, [
            "capacity_class",
            "btu_class",
            "BTU класс",
            "Класс BTU",
            "BTU",
            "БТЕ",
            "Мощность BTU",
        ]),
    );
    if (capacityClass) return `BTU ${capacityClass}`;

    const coolingKw = parseSpecNumber(
        getSpecValue(product, ["capacity_cooling_kw", "Мощность охлаждения"]),
    );
    if (coolingKw && coolingKw > 0) return `${formatDecimal(coolingKw)} кВт`;

    const textArea = asText(rawArea);
    return textArea ? `до ${textArea}` : "";
};

const getProductSeriesKey = (product: BrandSeriesProduct) => {
    const title = getProductSeriesTitle(product);
    if (!title) return "";
    return asText(product.series?.slug) || slugifySeriesFallback(title) || title.toLowerCase();
};

const getSeriesPreviewProducts = <T extends BrandSeriesProduct>(items: T[]) => {
    const seen = new Set<string>();
    const seenProducts = new Set<string>();
    const preview: T[] = [];
    for (const item of items) {
        const powerLabel = formatProductPowerLabel(item);
        const key = powerLabel || item.slug || item.title;
        if (seen.has(key)) continue;
        seen.add(key);
        seenProducts.add(item.slug || item.title);
        preview.push(item);
        if (preview.length >= 4) break;
    }

    const targetPreviewCount = Math.min(4, items.length);
    for (const item of items) {
        if (preview.length >= targetPreviewCount) break;
        const productKey = item.slug || item.title;
        if (seenProducts.has(productKey)) continue;
        seenProducts.add(productKey);
        preview.push(item);
    }

    return preview.length > 0 ? preview : items.slice(0, 4);
};

export const formatSeriesProductCount = (count: number) => {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return `${count} модель`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} модели`;
    return `${count} моделей`;
};

const sortSeriesGroups = <T extends { title: string; products: BrandSeriesProduct[] }>(groups: T[]) =>
    [...groups].sort((a, b) => {
        const countDiff = b.products.length - a.products.length;
        if (countDiff !== 0) return countDiff;
        return a.title.localeCompare(b.title, "ru");
    });

const getProductCatalogGroupKey = (product: BrandSeriesProduct): CatalogGroupKey => {
    const title = normalizeText(product.title);
    const type = normalizeText(getSpecValue(product, ["type", "Тип"]));
    const indoorType = normalizeText(getSpecValue(product, ["indoor_type", "Тип внутреннего блока"]));
    const joined = `${title} ${type} ${indoorType}`;

    if (hasTagSlug(product, "cat-multi") || joined.includes("мульти") || joined.includes("внутренний блок")) {
        return "multi";
    }
    if (hasTagSlug(product, "cat-industrial") || joined.includes("полупром") || joined.includes("кассет") || joined.includes("каналь") || joined.includes("напольно")) {
        return "industrial";
    }
    if (joined.includes("мобиль")) {
        return "mobile";
    }
    if (hasTagSlug(product, "cat-household") || hasTagSlug(product, "wall") || joined.includes("сплит-система")) {
        return "household";
    }
    return "other";
};

const inferSeriesVariantToken = (products: BrandSeriesProduct[]) => {
    const tokenCounts = new Map<string, number>();
    for (const product of products) {
        const text = `${product.title} ${product.slug}`.toUpperCase();
        const matches = text.match(/\b[A-Z]{1,4}\d{2,4}[A-Z]{1,4}\b/g) || [];
        for (const token of matches) {
            if (/^(TAC|FMA|TCA|TCB|TCC|TUB)\d/.test(token)) continue;
            tokenCounts.set(token, (tokenCounts.get(token) || 0) + 1);
        }
    }
    return [...tokenCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] || "";
};

const getDisplayTitle = (title: string, products: BrandSeriesProduct[], duplicateTitleCount: number) => {
    if (duplicateTitleCount <= 1) return title;
    const token = inferSeriesVariantToken(products);
    return token && !normalizeText(title).includes(normalizeText(token)) ? `${title} ${token}` : title;
};

const getDistinctFeaturesFactory = (rawSeriesGroups: Array<{ features: string[] }>) => {
    const featureCounts = rawSeriesGroups.reduce((counts, group) => {
        const uniqueFeatures = new Set(group.features.map((feature) => normalizeText(feature)).filter(Boolean));
        uniqueFeatures.forEach((feature) => counts.set(feature, (counts.get(feature) || 0) + 1));
        return counts;
    }, new Map<string, number>());
    const commonFeatureThreshold = Math.max(2, Math.ceil(rawSeriesGroups.length * 0.65));

    return (features: string[]) => {
        const distinct = features.filter((feature) => (featureCounts.get(normalizeText(feature)) || 0) < commonFeatureThreshold);
        return (distinct.length > 0 ? distinct : features).slice(0, 4);
    };
};

export const buildBrandSeriesCatalog = <T extends BrandSeriesProduct>(
    products: T[],
    popularProducts: T[],
    brandTitle: string,
): BrandSeriesCatalog<T> => {
    const catalogGroups = getCatalogGroups(brandTitle);
    const catalogGroupList = Object.values(catalogGroups);
    const seriesGroupsMap = new Map<string, Omit<BrandSeriesGroup<T>, "anchorId" | "catalogGroup" | "displayTitle" | "distinctFeatures" | "previewProducts">>();
    const seriesSourceProducts = popularProducts.length > 0 ? popularProducts : products;
    const productsWithoutSeries: T[] = [];

    for (const product of seriesSourceProducts) {
        const title = getProductSeriesTitle(product);
        const key = getProductSeriesKey(product);

        if (!title || !key) {
            productsWithoutSeries.push(product);
            continue;
        }

        if (!seriesGroupsMap.has(key)) {
            const galleryImages = normalizeSeriesGalleryImages(product.series);
            const featureBlocks = normalizeSeriesFeatureBlocks(product.series?.feature_blocks);
            const brandFeatures = normalizeSeriesBrandFeatures(product.series?.brand_features);
            const contentBlocks = normalizeSeriesContentBlocks(product.series?.content_blocks);
            seriesGroupsMap.set(key, {
                key,
                title,
                tagline: asText(product.series?.tagline),
                shortDescription: asText(product.series?.short_description),
                description: asText(product.series?.description),
                heroImage: asText(product.series?.hero_image),
                galleryImages,
                features: normalizeSeriesFeatures(product.series?.features),
                brandFeatures,
                featureBlocks,
                contentBlocks,
                footnotes: normalizeSeriesFeatures(product.series?.footnotes),
                primaryImage: "",
                visualFeatureBlocks: [],
                catalogGroupKey: getProductCatalogGroupKey(product),
                products: [],
            });
        }

        const group = seriesGroupsMap.get(key);
        if (group) {
            if (!group.tagline) group.tagline = asText(product.series?.tagline);
            if (!group.shortDescription) group.shortDescription = asText(product.series?.short_description);
            if (!group.description) group.description = asText(product.series?.description);
            if (!group.heroImage) group.heroImage = asText(product.series?.hero_image);
            if (group.galleryImages.length === 0) {
                group.galleryImages = normalizeSeriesGalleryImages(product.series);
            }
            if (group.features.length === 0) {
                group.features = normalizeSeriesFeatures(product.series?.features);
            }
            if (group.brandFeatures.length === 0) {
                group.brandFeatures = normalizeSeriesBrandFeatures(product.series?.brand_features);
            }
            if (group.featureBlocks.length === 0) {
                group.featureBlocks = normalizeSeriesFeatureBlocks(product.series?.feature_blocks);
            }
            if (group.contentBlocks.length === 0) {
                group.contentBlocks = normalizeSeriesContentBlocks(product.series?.content_blocks);
            }
            if (group.footnotes.length === 0) {
                group.footnotes = normalizeSeriesFeatures(product.series?.footnotes);
            }
            group.products.push(product);
        }
    }

    const rawSeriesGroups = sortSeriesGroups(Array.from(seriesGroupsMap.values()));
    const seriesTitleCounts = rawSeriesGroups.reduce((counts, group) => {
        const key = normalizeText(group.title);
        counts.set(key, (counts.get(key) || 0) + 1);
        return counts;
    }, new Map<string, number>());
    const getDistinctFeatures = getDistinctFeaturesFactory(rawSeriesGroups);
    const seriesGroups = rawSeriesGroups.map((group, index) => {
        const normalizedGroup = {
            ...group,
            primaryImage: getPrimarySeriesImage(group),
            visualFeatureBlocks: buildVisualFeatureBlocks(group),
        };
        return {
            ...normalizedGroup,
            anchorId: `series-${slugifySeriesFallback(group.key || group.title) || index + 1}`,
            catalogGroup: catalogGroups[group.catalogGroupKey],
            displayTitle: getDisplayTitle(group.title, group.products, seriesTitleCounts.get(normalizeText(group.title)) || 0),
            distinctFeatures: getDistinctFeatures(group.features),
            previewProducts: getSeriesPreviewProducts(group.products),
        };
    });
    const seriesGroupsByCatalog = catalogGroupList
        .map((catalogGroup) => ({
            ...catalogGroup,
            series: seriesGroups.filter((group) => group.catalogGroupKey === catalogGroup.key),
        }))
        .filter((catalogGroup) => catalogGroup.series.length > 0);
    const productsWithoutSeriesByCatalog = catalogGroupList
        .map((catalogGroup) => ({
            ...catalogGroup,
            products: productsWithoutSeries.filter((product) => getProductCatalogGroupKey(product) === catalogGroup.key),
        }))
        .filter((catalogGroup) => catalogGroup.products.length > 0);

    return {
        seriesSourceProducts,
        seriesGroups,
        seriesGroupsByCatalog,
        productsWithoutSeriesByCatalog,
    };
};
