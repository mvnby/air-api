import assert from 'node:assert/strict';

import {
  buildBrandMetaDescription,
  buildBrandSeoTitle,
  buildCanonicalUrl,
  buildProductMetaDescription,
  normalizeCanonicalPath,
  sanitizeSeoText,
} from '../src/utils/seo.js';

const haier = {
  title: 'Сплит-система Haier Tundra HSU-12HTT03/R3',
  brand: { title: 'Haier', slug: 'haier' },
  area: 35,
  power_cooling: 3.5,
  is_inverter: false,
  tags: [
    { title: 'Бытовые кондиционеры', slug: 'cat-household', group: { slug: 'category' } },
  ],
};

const mdv = {
  title: 'MDV OP Smart Heat Pump MDSOPS-09HRFN8/MDOOPS-09HFN8',
  brand: { title: 'MDV', slug: 'mdv' },
  area: 25,
  power_cooling: 2.63,
  is_inverter: true,
  tags: [
    { title: 'Бытовые кондиционеры', slug: 'cat-household', group: { slug: 'category' } },
  ],
};

const haierDescription = buildProductMetaDescription(haier);
const mdvDescription = buildProductMetaDescription(mdv);

assert.match(haierDescription, /Haier Tundra/);
assert.match(haierDescription, /Витебске/);
assert.ok(haierDescription.length <= 170, haierDescription);
assert.ok(mdvDescription.length <= 170, mdvDescription);
assert.notEqual(haierDescription, mdvDescription);
assert.notEqual(haierDescription, 'Кондиционеры в Витебске. Продажа, монтаж, обслуживание');

const htmlText = sanitizeSeoText('<b>Haier&nbsp;Home</b> &amp; монтаж');
assert.equal(htmlText, 'Haier Home & монтаж');
assert.equal(normalizeCanonicalPath('/product/split-sistema-haier-tundra'), '/product/split-sistema-haier-tundra/');
assert.equal(normalizeCanonicalPath('/index.php?_route_=split/haier/lightera/'), '/split/haier/lightera/');
assert.equal(normalizeCanonicalPath('https://mvn.by/catalog?tag_slugs=cat-multi'), '/catalog/');
assert.equal(buildCanonicalUrl('/brands/haier', 'https://mvn.by'), 'https://mvn.by/brands/haier/');

const longDescription = buildProductMetaDescription({
  title: 'Очень длинное название кондиционера с большим количеством характеристик и длинным техническим обозначением модели ABCDEFG-1234567890-EXTRA-LONG',
  area: 55,
  power_cooling: 5.2,
  is_inverter: true,
});
assert.ok(longDescription.length <= 170, longDescription);

assert.equal(buildBrandSeoTitle({ title: 'TCL' }), 'Кондиционеры TCL: купить в Витебске');
const brandDescription = buildBrandMetaDescription({ title: 'TCL' });
assert.match(brandDescription, /Кондиционеры TCL/);
assert.ok(brandDescription.length <= 170, brandDescription);

console.log('SEO helper tests passed');
