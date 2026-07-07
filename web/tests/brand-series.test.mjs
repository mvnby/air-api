import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import ts from "typescript";

const sourceUrl = new URL("../src/utils/brand-series.ts", import.meta.url);
const source = await readFile(sourceUrl, "utf8");
const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { buildBrandSeriesCatalog } = await import(moduleUrl);

describe("brand series catalog", () => {
    it("keeps rich series media and feature blocks structured", () => {
        const products = [
            {
                title: "LG Eco 09",
                slug: "lg-eco-09",
                area: 25,
                series: {
                    title: "Eco Smart",
                    slug: "eco-smart",
                    tagline: "Практичная инверторная серия",
                    short_description: "Для квартир и офисов.",
                    hero_image: "/media/series/eco-hero.webp",
                    gallery_images: ["/media/series/eco-gallery.webp"],
                    features: ["Dual Inverter", "Wi-Fi"],
                    brand_features: [
                        {
                            id: 2,
                            title: "Gold Fin",
                            slug: "gold-fin",
                            text: "Защита теплообменника.",
                            image_url: "/media/features/gold-fin.webp",
                            icon: "shield",
                            footnote: "Зависит от модели",
                            sort_order: 20,
                        },
                    ],
                    feature_blocks: [
                        {
                            title: "Dual Inverter",
                            text: "Компрессор регулирует мощность.",
                            image_url: "/media/features/dual-inverter.webp",
                            icon: "speed",
                            footnote: "Гарантия зависит от условий.",
                        },
                    ],
                    content_blocks: [
                        {
                            kind: "image_text",
                            title: "Тихая работа",
                            text: "Подходит для спальни.",
                            image_url: "/media/features/quiet.webp",
                            layout: "text_right",
                        },
                    ],
                    footnotes: ["Точные характеристики зависят от модели."],
                },
                specs: { type: "сплит-система" },
                tags: [{ slug: "cat-household", is_public: true }],
            },
        ];

        const catalog = buildBrandSeriesCatalog(products, products, "LG");
        const group = catalog.seriesGroups[0];

        assert.equal(group.primaryImage, "/media/series/eco-hero.webp");
        assert.deepEqual(group.galleryImages, ["/media/series/eco-hero.webp", "/media/series/eco-gallery.webp"]);
        assert.equal(group.brandFeatures[0].title, "Gold Fin");
        assert.equal(group.featureBlocks[0].title, "Dual Inverter");
        assert.equal(group.contentBlocks[0].title, "Тихая работа");
        assert.deepEqual(group.footnotes, ["Точные характеристики зависят от модели."]);
        assert.deepEqual(
            group.visualFeatureBlocks.map((block) => [block.source, block.title]),
            [
                ["feature_block", "Dual Inverter"],
                ["brand_feature", "Gold Fin"],
                ["content_block", "Тихая работа"],
            ],
        );
    });
});
