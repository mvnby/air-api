import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import ts from "typescript";

const transpile = async (relativePath) => {
    const source = await readFile(new URL(relativePath, import.meta.url), "utf8");
    return ts.transpileModule(source, {
        compilerOptions: {
            module: ts.ModuleKind.ESNext,
            target: ts.ScriptTarget.ES2022,
        },
    }).outputText;
};

const productDisplaySource = await transpile("../src/utils/product-display.ts");
const productDisplayUrl = `data:text/javascript;base64,${Buffer.from(productDisplaySource).toString("base64")}`;
const catalogSeoSource = await transpile("../src/utils/catalog-seo.ts");
const catalogSeoWithResolvedImport = catalogSeoSource.replace(
    /from ["']\.\/product-display["'];?/,
    `from "${productDisplayUrl}";`,
);
assert.notEqual(catalogSeoWithResolvedImport, catalogSeoSource, "product-display import was not resolved");
const catalogSeoUrl = `data:text/javascript;base64,${Buffer.from(catalogSeoWithResolvedImport).toString("base64")}`;
const { buildProductSchema, getSchemaAvailability } = await import(catalogSeoUrl);

describe("catalog structured data", () => {
    it("marks explicitly unavailable products as OutOfStock", () => {
        const product = {
            title: "Unavailable AC",
            description: "Unavailable test product",
            image: "https://cdn.mvn.by/product.webp",
            price: 623,
            currency: "BYN",
            availability_status: "out_of_stock",
            vitebsk_qty: 0,
            minsk_qty: 0,
        };

        assert.equal(getSchemaAvailability(product), "https://schema.org/OutOfStock");
        assert.equal(
            buildProductSchema(product).offers.availability,
            "https://schema.org/OutOfStock",
        );
    });

    it("uses actual stock quantities for InStock", () => {
        const schema = buildProductSchema({
            title: "Available AC",
            description: "Available test product",
            image: "https://cdn.mvn.by/product.webp",
            price: 1000,
            vitebsk_qty: 1,
            minsk_qty: 0,
        });

        assert.equal(schema.offers.availability, "https://schema.org/InStock");
    });
});
