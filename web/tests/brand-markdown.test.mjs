import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import ts from "typescript";

const sourceUrl = new URL("../src/utils/brands.ts", import.meta.url);
const source = await readFile(sourceUrl, "utf8");
const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
        module: ts.ModuleKind.ESNext,
        target: ts.ScriptTarget.ES2022,
    },
});
const moduleUrl = `data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`;
const { getBrandIntroPlainText, renderBrandIntroMarkdown } = await import(moduleUrl);

describe("brand intro markdown rendering", () => {
    it("escapes raw HTML before rendering", () => {
        const html = renderBrandIntroMarkdown('Intro <script>alert("x")</script> <b>bold</b>');

        assert.equal(html.includes("<script>"), false);
        assert.equal(html.includes("<b>bold</b>"), false);
        assert.match(html, /&lt;script&gt;alert\(&quot;x&quot;\)&lt;\/script&gt;/);
        assert.match(html, /&lt;b&gt;bold&lt;\/b&gt;/);
    });

    it("does not emit href attributes for unsafe links", () => {
        const html = renderBrandIntroMarkdown(
            "Bad [script](javascript:alert) and [protocol](//evil.example/path)."
        );

        assert.equal(html.includes('href="javascript:'), false);
        assert.equal(html.includes('href="//evil.example'), false);
        assert.match(html, /Bad script and protocol\./);
    });

    it("renders safe links", () => {
        const html = renderBrandIntroMarkdown(
            "Links: [http](http://example.com), [https](https://example.com/a?b=1&c=2), [relative](/brands/tcl/), [hash](#models), [mail](mailto:sales@example.com)."
        );

        assert.match(html, /<a href="http:\/\/example\.com" rel="noopener noreferrer">http<\/a>/);
        assert.match(html, /<a href="https:\/\/example\.com\/a\?b=1&amp;c=2" rel="noopener noreferrer">https<\/a>/);
        assert.match(html, /<a href="\/brands\/tcl\/" rel="noopener noreferrer">relative<\/a>/);
        assert.match(html, /<a href="#models" rel="noopener noreferrer">hash<\/a>/);
        assert.match(html, /<a href="mailto:sales@example\.com" rel="noopener noreferrer">mail<\/a>/);
    });

    it("renders paragraphs, lists, strong and emphasis", () => {
        const html = renderBrandIntroMarkdown("First **bold** and *em*.\n\n- one\n- two");

        assert.equal(
            html,
            "<p>First <strong>bold</strong> and <em>em</em>.</p><ul><li>one</li><li>two</li></ul>"
        );
    });

    it("strips markdown to plain text for previews", () => {
        const text = getBrandIntroPlainText(
            "Intro **bold** and *em* with [link](https://example.com).\n\n- one\n- two"
        );

        assert.equal(text, "Intro bold and em with link. one two");
    });
});
