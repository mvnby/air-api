const DEFAULT_BASE_URL = 'http://127.0.0.1:4321/__ssr-staging';

const rawBaseUrl = process.argv[2] || process.env.SSR_SMOKE_BASE_URL || DEFAULT_BASE_URL;
const baseUrl = new URL(rawBaseUrl.endsWith('/') ? rawBaseUrl : `${rawBaseUrl}/`);

const normalizeApiV1Base = (raw) => {
  const base = String(raw || '').trim().replace(/\/$/, '');
  if (!base) return '';
  if (base.endsWith('/api/v1')) return base;
  return `${base.replace(/\/api\/v1$/, '')}/api/v1`;
};

const apiBase = normalizeApiV1Base(
  process.env.SSR_SMOKE_API_URL ||
    process.env.INTERNAL_API_URL ||
    process.env.PUBLIC_API_URL ||
    'https://api.mvn.by/api/v1',
);
const basicAuth = String(process.env.SSR_SMOKE_BASIC_AUTH || '').trim();
const smokeHeaders = basicAuth
  ? { Authorization: `Basic ${Buffer.from(basicAuth).toString('base64')}` }
  : {};

const checked = [];
let expectedCatalogRevision = '';

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchApiFixture(url, label, attempts = 3) {
  let lastStatus = 'network-error';
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
      lastStatus = response.status;
    } catch (error) {
      lastStatus = error.message;
    }
    if (attempt < attempts) {
      await delay(300 * attempt);
    }
  }
  throw new Error(`${label} failed after ${attempts} attempt(s): ${lastStatus} ${url}`);
}

function resolveSmokeUrl(path) {
  const marker = new URL(path, 'http://smoke.local');
  const prefix = baseUrl.pathname.replace(/\/$/, '');
  const url = new URL(baseUrl.origin);
  url.pathname = `${prefix}${marker.pathname}`.replace(/\/{2,}/g, '/');
  url.search = marker.search;
  return url;
}

async function fetchRequired(url, label, options = {}) {
  const response = await fetch(url, {
    method: options.method || 'GET',
    headers: smokeHeaders,
    redirect: options.redirect || 'manual',
  });
  checked.push(`${label}: ${response.status} ${url}`);

  if (!response.ok) {
    throw new Error(`${label} failed with ${response.status}: ${url}`);
  }

  if (options.freshness) {
    const revision = response.headers.get('x-catalog-revision') || '';
    const cacheStatus = response.headers.get('x-web-data-cache') || '';
    if (!revision) {
      throw new Error(`${label} did not include X-Catalog-Revision: ${url}`);
    }
    if (!cacheStatus) {
      throw new Error(`${label} did not include X-Web-Data-Cache: ${url}`);
    }
    if (expectedCatalogRevision && revision !== expectedCatalogRevision) {
      throw new Error(
        `${label} revision mismatch: expected ${expectedCatalogRevision}, got ${revision}`,
      );
    }
    checked.push(`${label} freshness: revision=${revision} cache=${cacheStatus}`);
  }

  if (options.text) {
    return await response.text();
  }

  return response;
}

async function resolveCatalogRevision() {
  const revisionUrl = `${apiBase}/catalog/revision`;
  const response = await fetchApiFixture(revisionUrl, 'Catalog revision lookup');
  const data = await response.json();
  const revision = String(data?.revision ?? '').trim();
  if (!revision) {
    throw new Error(`Catalog revision lookup returned no revision: ${revisionUrl}`);
  }
  checked.push(`api revision: ${revision} ${revisionUrl}`);
  return revision;
}

function normalizeProductPath(value) {
  const clean = String(value || '').trim();
  if (!clean) return '';
  return clean.startsWith('/') ? clean : `/${clean}`;
}

function productSlugFromPath(path) {
  return String(path || '').match(/\/product\/([^/?#]+)/)?.[1] || '';
}

function normalizeBrandPath(value) {
  const clean = String(value || '').trim();
  if (!clean) return '';
  return clean.startsWith('/') ? clean : `/${clean}`;
}

function brandSlugFromPath(path) {
  return String(path || '').match(/\/brands\/([^/?#]+)/)?.[1] || '';
}

function priceTokens(value) {
  if (value === null || value === undefined || value === '') return [];
  const raw = String(value).trim();
  const numeric = Number(value);
  const tokens = new Set([raw, raw.replace(/\.0+$/, '')]);
  if (Number.isFinite(numeric)) {
    tokens.add(numeric.toLocaleString('ru-RU'));
    tokens.add(numeric.toLocaleString('ru-RU').replace(/\u00a0/g, ' '));
  }
  return [...tokens].filter(Boolean);
}

function assertPriceInHtml(html, product, label) {
  const tokens = priceTokens(product?.price);
  if (tokens.length === 0) return;
  if (!tokens.some((token) => html.includes(token))) {
    throw new Error(`${label} HTML does not include API price ${product.price}`);
  }
}

async function fetchProductBySlug(slug) {
  if (!slug) return null;
  try {
    const response = await fetchApiFixture(
      `${apiBase}/products/${encodeURIComponent(slug)}`,
      `Product lookup ${slug}`,
      2,
    );
    return await response.json();
  } catch {
    return null;
  }
}

async function fetchBrandBySlug(slug) {
  if (!slug) return null;
  try {
    const response = await fetchApiFixture(
      `${apiBase}/content/brands/${encodeURIComponent(slug)}`,
      `Brand lookup ${slug}`,
      2,
    );
    return await response.json();
  } catch {
    return null;
  }
}

async function resolveCatalogProductFixture() {
  const catalogUrl = `${apiBase}/catalog?page=1&limit=20&sort=recommended&tag_slugs=cat-household`;
  const response = await fetchApiFixture(catalogUrl, 'Catalog smoke lookup');
  const data = await response.json();
  const product = data?.items?.find((item) => item?.slug);
  if (!product) {
    throw new Error(`Catalog smoke lookup returned no product slug: ${catalogUrl}`);
  }

  return {
    path: `/product/${product.slug}/`,
    slug: product.slug,
    title: String(product.title || '').trim(),
    price: product.price,
  };
}

async function resolveProductFixture(catalogFixture) {
  const configured = String(process.env.SSR_SMOKE_PRODUCT_PATH || '').trim();
  if (configured) {
    const path = normalizeProductPath(configured);
    const product = await fetchProductBySlug(productSlugFromPath(path));
    return {
      path,
      slug: product?.slug || productSlugFromPath(path),
      title: String(product?.title || '').trim(),
      price: product?.price,
    };
  }

  return catalogFixture;
}

async function resolveBrandFixture() {
  const configured = String(process.env.SSR_SMOKE_BRAND_PATH || '').trim();
  if (configured) {
    const path = normalizeBrandPath(configured);
    const brand = await fetchBrandBySlug(brandSlugFromPath(path));
    return {
      path,
      slug: brand?.slug || brandSlugFromPath(path),
      title: String(brand?.title || '').trim(),
      productsCount: brand?.products_count,
    };
  }

  const brandsUrl = `${apiBase}/content/brands`;
  const response = await fetchApiFixture(brandsUrl, 'Brand smoke lookup');
  const data = await response.json();
  const brand = data?.find((item) => item?.slug);
  if (!brand) {
    throw new Error(`Brand smoke lookup returned no slug: ${brandsUrl}`);
  }

  return {
    path: `/brands/${brand.slug}/`,
    slug: brand.slug,
    title: String(brand.title || '').trim(),
    productsCount: brand.products_count,
  };
}

async function fetchExpectedNotFound(path, label) {
  const response = await fetch(resolveSmokeUrl(path), {
    headers: smokeHeaders,
    redirect: 'manual',
  });
  checked.push(`${label}: ${response.status} ${resolveSmokeUrl(path)}`);
  if (response.status !== 404) {
    throw new Error(`${label} expected 404, got ${response.status}: ${path}`);
  }

  const revision = response.headers.get('x-catalog-revision') || '';
  const cacheStatus = response.headers.get('x-web-data-cache') || '';
  if (!revision) {
    throw new Error(`${label} did not include X-Catalog-Revision: ${path}`);
  }
  if (!cacheStatus) {
    throw new Error(`${label} did not include X-Web-Data-Cache: ${path}`);
  }
  if (expectedCatalogRevision && revision !== expectedCatalogRevision) {
    throw new Error(`${label} revision mismatch: expected ${expectedCatalogRevision}, got ${revision}`);
  }
  checked.push(`${label} freshness: revision=${revision} cache=${cacheStatus}`);
}

function resolveAssetUrl(assetRef) {
  if (!assetRef) {
    throw new Error('No /_astro asset reference found in SSR HTML.');
  }

  return new URL(assetRef, baseUrl);
}

const checks = [
  ['/', 'home'],
  ['/catalog/?area_max=35&tag_slugs=cat-household', 'catalog query'],
];

try {
  expectedCatalogRevision = await resolveCatalogRevision();
  const catalogFixture = await resolveCatalogProductFixture();
  const productFixture = await resolveProductFixture(catalogFixture);
  const brandFixture = await resolveBrandFixture();
  const homeHtml = await fetchRequired(resolveSmokeUrl('/'), 'home', { text: true });

  const catalogHtml = await fetchRequired(resolveSmokeUrl('/catalog/'), 'catalog', {
    text: true,
    freshness: true,
  });
  if (!catalogHtml.includes(catalogFixture.path) && !catalogHtml.includes(`/product/${catalogFixture.slug}`)) {
    throw new Error(`catalog HTML does not include API product ${catalogFixture.path}`);
  }
  if (catalogFixture.title && !catalogHtml.includes(catalogFixture.title)) {
    throw new Error(`catalog HTML does not include API product title: ${catalogFixture.title}`);
  }
  assertPriceInHtml(catalogHtml, catalogFixture, 'catalog');

  const expectedCatalogProductPath = normalizeProductPath(process.env.SSR_SMOKE_EXPECT_CATALOG_PRODUCT_PATH || '');
  if (
    expectedCatalogProductPath &&
    !catalogHtml.includes(expectedCatalogProductPath) &&
    !catalogHtml.includes(expectedCatalogProductPath.replace(/\/$/, ''))
  ) {
    throw new Error(`catalog HTML does not include expected product path: ${expectedCatalogProductPath}`);
  }

  const unpublishedProductPath = normalizeProductPath(process.env.SSR_SMOKE_UNPUBLISHED_PRODUCT_PATH || '');
  if (
    unpublishedProductPath &&
    (catalogHtml.includes(unpublishedProductPath) || catalogHtml.includes(unpublishedProductPath.replace(/\/$/, '')))
  ) {
    throw new Error(`catalog HTML still includes unpublished product path: ${unpublishedProductPath}`);
  }

  for (const [path, label] of checks.slice(1)) {
    await fetchRequired(resolveSmokeUrl(path), label, { freshness: true });
  }

  const brandsHtml = await fetchRequired(resolveSmokeUrl('/brands/'), 'brands', {
    text: true,
    freshness: true,
  });
  if (brandFixture.title && !brandsHtml.includes(brandFixture.title)) {
    throw new Error(`brands HTML does not include API brand title: ${brandFixture.title}`);
  }
  if (
    brandFixture.productsCount !== null &&
    brandFixture.productsCount !== undefined &&
    !brandsHtml.includes(String(brandFixture.productsCount))
  ) {
    throw new Error(`brands HTML does not include API brand count: ${brandFixture.productsCount}`);
  }

  const brandHtml = await fetchRequired(resolveSmokeUrl(brandFixture.path), `brand ${brandFixture.path}`, {
    text: true,
    freshness: true,
  });
  if (brandFixture.title && !brandHtml.includes(brandFixture.title)) {
    throw new Error(`brand page HTML does not include API brand title: ${brandFixture.title}`);
  }

  const productHtml = await fetchRequired(resolveSmokeUrl(productFixture.path), `product ${productFixture.path}`, {
    text: true,
    freshness: true,
  });
  if (productFixture.title && !productHtml.includes(productFixture.title)) {
    throw new Error(`product HTML does not include API product title: ${productFixture.title}`);
  }
  assertPriceInHtml(productHtml, productFixture, 'product');

  if (unpublishedProductPath) {
    await fetchExpectedNotFound(unpublishedProductPath, `unpublished product ${unpublishedProductPath}`);
  }

  const assetRef = homeHtml.match(/(?:href|src)="([^"]*\/_astro\/[^"]+)"/)?.[1];
  const assetUrl = resolveAssetUrl(assetRef);
  await fetchRequired(assetUrl, 'astro asset', { method: 'GET' });

  console.log('SSR staging smoke passed.');
  for (const line of checked) {
    console.log(`- ${line}`);
  }
} catch (error) {
  console.error('SSR staging smoke failed.');
  for (const line of checked) {
    console.error(`- ${line}`);
  }
  console.error(error.message);
  process.exit(1);
}
