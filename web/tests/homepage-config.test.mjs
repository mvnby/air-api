import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import ts from "typescript";

const importTypeScriptModule = async (relativePath) => {
    const sourceUrl = new URL(relativePath, import.meta.url);
    const source = await readFile(sourceUrl, "utf8");
    const { outputText } = ts.transpileModule(source, {
        compilerOptions: {
            module: ts.ModuleKind.ESNext,
            target: ts.ScriptTarget.ES2022,
        },
    });
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
    return import(moduleUrl);
};

const homepage = await importTypeScriptModule("../src/config/homepage.ts");
const homeSelection = await importTypeScriptModule(
    "../src/config/home-selection.ts",
);
const productCompare = await importTypeScriptModule(
    "../src/utils/product-compare.ts",
);
const virtualCategories = await importTypeScriptModule(
    "../src/config/virtual-categories.ts",
);
const [homepageSource, installationSource, contactsSource] = await Promise.all([
    readFile(new URL("../src/pages/index.astro", import.meta.url), "utf8"),
    readFile(
        new URL("../src/pages/montaj-konditionerov.astro", import.meta.url),
        "utf8",
    ),
    readFile(new URL("../src/pages/contacts.astro", import.meta.url), "utf8"),
]);

describe("homepage conversion routes", () => {
    it("keeps four distinct intent routes", () => {
        assert.equal(homepage.HOMEPAGE_INTENTS.length, 4);
        assert.equal(
            new Set(homepage.HOMEPAGE_INTENTS.map((item) => item.href)).size,
            4,
        );
    });

    it("uses only existing virtual categories for quick picks", () => {
        const supportedPaths = new Set(
            virtualCategories.VIRTUAL_CATEGORIES.map(
                (item) => `/catalog/${item.slug}/`,
            ),
        );

        for (const item of homepage.HOMEPAGE_QUICK_PICKS) {
            assert.equal(
                supportedPaths.has(item.href),
                true,
                `Unsupported quick-pick route: ${item.href}`,
            );
        }
    });

    it("keeps analytics event names distinct and free of PII fields", () => {
        const events = Object.values(homepage.HOMEPAGE_ANALYTICS_EVENTS);
        assert.equal(new Set(events).size, events.length);
        assert.equal(events.every((event) => event.startsWith("home_")), true);
    });

    it("keeps CTA destination anchors available", () => {
        assert.match(installationSource, /id="installation-request"/);
        assert.match(contactsSource, /id="contact-form"/);
        assert.match(homepageSource, /fitCheckHref="\/contacts\/#contact-form"/);
    });

    it("does not restore unverified homepage proof claims", () => {
        assert.doesNotMatch(homepageSource, /500\+|20\+ лет|гарантией/iu);
    });

    it("maps selector answers to supported catalog filters", () => {
        const result = homeSelection.buildHomeSelectionResult({
            rooms: "single",
            area: 25,
            priority: "silent",
            inverter: true,
        });
        const url = new URL(result.href, "https://mvn.by");

        assert.equal(url.pathname, "/catalog/");
        assert.equal(url.searchParams.get("area_max"), "25");
        assert.equal(url.searchParams.get("tag_slugs"), "noise-silent");
        assert.equal(url.searchParams.get("is_inverter"), "true");
    });

    it("routes multi-room selection to the existing multi-split category", () => {
        const result = homeSelection.buildHomeSelectionResult({
            rooms: "multiple",
            area: 50,
            priority: "wifi",
            inverter: false,
        });

        assert.equal(result.href, "/catalog/multi-split/");
    });

    it("normalizes comparison state and enforces the three-product limit", () => {
        const items = productCompare.normalizeCompareItems([
            {
                slug: "one",
                title: "One",
                snapshot: { slug: "different", title: "Different", price: 1000 },
            },
            { slug: "one", title: "Duplicate" },
            { slug: "../../bad", title: "Bad" },
            { slug: "two", title: "Two" },
            { slug: "three", title: "Three" },
            { slug: "four", title: "Four" },
        ]);

        assert.deepEqual(items.map((item) => item.slug), ["one", "two", "three"]);
        assert.equal(items[0].snapshot.slug, "one");
        assert.equal(
            productCompare.buildCompareUrl(items),
            "/compare/?products=one%2Ctwo%2Cthree",
        );
    });
});
