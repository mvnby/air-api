export const PUBLIC_CATALOG_PAGE_SIZE = 100;

const asNonNegativeInteger = (value, field, context) => {
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 0) {
        throw new Error(`[${context}] Invalid catalog meta.${field}: ${value}`);
    }
    return parsed;
};

export async function collectCatalogPages(
    fetchPage,
    {
        params = {},
        pageSize = PUBLIC_CATALOG_PAGE_SIZE,
        context = "catalog pagination",
    } = {},
) {
    if (typeof fetchPage !== "function") {
        throw new TypeError(`[${context}] fetchPage must be a function`);
    }
    if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > PUBLIC_CATALOG_PAGE_SIZE) {
        throw new RangeError(
            `[${context}] pageSize must be between 1 and ${PUBLIC_CATALOG_PAGE_SIZE}`,
        );
    }

    const itemsBySlug = new Map();
    let expectedTotal = null;
    let expectedPages = null;
    let firstMeta = null;
    let page = 1;

    do {
        const payload = await fetchPage({
            ...params,
            page,
            limit: pageSize,
        });
        if (!payload || !Array.isArray(payload.items) || !payload.meta) {
            throw new Error(`[${context}] Page ${page} returned an invalid catalog payload`);
        }

        const total = asNonNegativeInteger(payload.meta.total, "total", context);
        const apiPage = asNonNegativeInteger(payload.meta.page, "page", context);
        const apiLimit = asNonNegativeInteger(payload.meta.limit, "limit", context);
        const apiPages = asNonNegativeInteger(payload.meta.pages, "pages", context);
        const calculatedPages = total === 0 ? 0 : Math.ceil(total / pageSize);

        if (apiPage !== page || apiLimit !== pageSize || apiPages !== calculatedPages) {
            throw new Error(
                `[${context}] Inconsistent page metadata on page ${page}: ` +
                `page=${apiPage}, limit=${apiLimit}, pages=${apiPages}, expected_pages=${calculatedPages}`,
            );
        }

        if (expectedTotal === null) {
            expectedTotal = total;
            expectedPages = calculatedPages;
            firstMeta = payload.meta;
        } else if (total !== expectedTotal || calculatedPages !== expectedPages) {
            throw new Error(
                `[${context}] Catalog count changed while paging: ` +
                `expected ${expectedTotal}, received ${total} on page ${page}`,
            );
        }

        for (const item of payload.items) {
            const slug = String(item?.slug || "").trim();
            if (!slug) {
                throw new Error(`[${context}] Page ${page} contains an item without a slug`);
            }
            if (!itemsBySlug.has(slug)) {
                itemsBySlug.set(slug, item);
            }
        }

        page += 1;
    } while (page <= expectedPages);

    if (itemsBySlug.size !== expectedTotal) {
        throw new Error(
            `[${context}] Catalog route count mismatch: ` +
            `expected ${expectedTotal}, received ${itemsBySlug.size} unique slugs`,
        );
    }

    return {
        items: [...itemsBySlug.values()],
        meta: {
            ...(firstMeta || {}),
            total: expectedTotal,
            page: 1,
            limit: pageSize,
            pages: expectedPages,
        },
    };
}
