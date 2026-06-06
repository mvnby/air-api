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

  if (options.text) {
    return await response.text();
  }

  return response;
}

async function resolveProductPath() {
  const configured = String(process.env.SSR_SMOKE_PRODUCT_PATH || '').trim();
  if (configured) return configured.startsWith('/') ? configured : `/${configured}`;

  const catalogUrl = `${apiBase}/catalog?limit=1`;
  const response = await fetch(catalogUrl);
  if (!response.ok) {
    throw new Error(`Product smoke lookup failed with ${response.status}: ${catalogUrl}`);
  }

  const data = await response.json();
  const slug = data?.items?.find((item) => item?.slug)?.slug;
  if (!slug) {
    throw new Error(`Product smoke lookup returned no slug: ${catalogUrl}`);
  }

  return `/product/${slug}/`;
}

function resolveAssetUrl(assetRef) {
  if (!assetRef) {
    throw new Error('No /_astro asset reference found in SSR HTML.');
  }

  return new URL(assetRef, baseUrl);
}

const checks = [
  ['/', 'home'],
  ['/catalog/', 'catalog'],
  ['/catalog/?area_max=35&tag_slugs=cat-household', 'catalog query'],
  ['/brands/', 'brands'],
];

try {
  const homeHtml = await fetchRequired(resolveSmokeUrl('/'), 'home', { text: true });

  for (const [path, label] of checks.slice(1)) {
    await fetchRequired(resolveSmokeUrl(path), label);
  }

  const productPath = await resolveProductPath();
  await fetchRequired(resolveSmokeUrl(productPath), `product ${productPath}`);

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
