import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
    collectCatalogPages,
    PUBLIC_CATALOG_PAGE_SIZE,
} from "../src/utils/catalog-pagination.js";

const makeItems = (start, count) => Array.from(
    { length: count },
    (_, index) => ({ slug: `product-${start + index}` }),
);

describe("catalog pagination", () => {
    it("collects every page with the public page-size cap", async () => {
        const allItems = makeItems(1, 205);
        const calls = [];
        const result = await collectCatalogPages(async ({ page, limit }) => {
            calls.push({ page, limit });
            const start = (page - 1) * limit;
            return {
                items: allItems.slice(start, start + limit),
                meta: { total: allItems.length, page, limit, pages: 3 },
            };
        });

        assert.deepEqual(calls, [
            { page: 1, limit: PUBLIC_CATALOG_PAGE_SIZE },
            { page: 2, limit: PUBLIC_CATALOG_PAGE_SIZE },
            { page: 3, limit: PUBLIC_CATALOG_PAGE_SIZE },
        ]);
        assert.equal(result.items.length, 205);
        assert.equal(new Set(result.items.map((item) => item.slug)).size, 205);
        assert.deepEqual(result.meta, {
            total: 205,
            page: 1,
            limit: 100,
            pages: 3,
        });
    });

    it("deduplicates slugs and hard-fails when a route would be omitted", async () => {
        await assert.rejects(
            collectCatalogPages(async ({ page, limit }) => ({
                items: page === 1
                    ? [{ slug: "one" }, { slug: "two" }]
                    : [{ slug: "two" }],
                meta: { total: 3, page, limit, pages: 2 },
            }), { pageSize: 2, context: "test routes" }),
            /Catalog route count mismatch: expected 3, received 2 unique slugs/,
        );
    });

    it("hard-fails when the API total changes between pages", async () => {
        await assert.rejects(
            collectCatalogPages(async ({ page, limit }) => ({
                items: [{ slug: `page-${page}` }],
                meta: {
                    total: page === 1 ? 2 : 3,
                    page,
                    limit,
                    pages: page === 1 ? 2 : 3,
                },
            }), { pageSize: 1 }),
            /Catalog count changed while paging/,
        );
    });

    it("refuses to exceed the backend public cap", async () => {
        await assert.rejects(
            collectCatalogPages(async () => null, { pageSize: 101 }),
            /pageSize must be between 1 and 100/,
        );
    });
});
