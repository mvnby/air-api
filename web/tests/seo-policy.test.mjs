import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import {
    EXCLUDED_SITEMAP_PATHS,
    shouldIncludeSitemapPage,
} from "../sitemap-filter.mjs";

const webRoot = fileURLToPath(new URL("../", import.meta.url));
const transactionalPages = new Map([
    ["/cart/", "src/pages/cart.astro"],
    ["/checkout/", "src/pages/checkout.astro"],
    ["/compare/", "src/pages/compare.astro"],
    ["/success/", "src/pages/success.astro"],
]);

const collectAstroFiles = async (directory) => {
    const entries = await readdir(directory, { withFileTypes: true });
    const files = [];
    for (const entry of entries) {
        const absolutePath = join(directory, entry.name);
        if (entry.isDirectory()) {
            files.push(...await collectAstroFiles(absolutePath));
        } else if (extname(entry.name) === ".astro") {
            files.push(absolutePath);
        }
    }
    return files;
};

describe("storefront SEO policy", () => {
    it("keeps transactional pages noindex and out of the sitemap", async () => {
        assert.deepEqual(
            [...EXCLUDED_SITEMAP_PATHS].sort(),
            ["/404/", "/cart/", "/checkout/", "/compare/", "/success/"].sort(),
        );

        for (const [pathname, relativeSource] of transactionalPages) {
            const source = await readFile(join(webRoot, relativeSource), "utf8");
            assert.match(source, /robots="noindex,follow"/, `${pathname} must be noindex`);
            assert.equal(
                shouldIncludeSitemapPage(`https://mvn.by${pathname}`),
                false,
                `${pathname} must be excluded from the sitemap`,
            );
        }

        assert.equal(shouldIncludeSitemapPage("https://mvn.by/catalog/"), true);
    });

    it("does not embed raw JSON.stringify output with set:html", async () => {
        const astroFiles = await collectAstroFiles(join(webRoot, "src"));
        const offenders = [];
        for (const file of astroFiles) {
            const source = await readFile(file, "utf8");
            if (/set:html=\{JSON\.stringify\(/.test(source)) {
                offenders.push(file.slice(webRoot.length));
            }
        }

        assert.deepEqual(offenders, []);
    });
});
