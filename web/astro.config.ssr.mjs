import { defineConfig } from 'astro/config';
import vue from '@astrojs/vue';
import mdx from '@astrojs/mdx';
import tailwind from '@astrojs/tailwind';
import sitemap from '@astrojs/sitemap';
import node from '@astrojs/node';
import { shouldIncludeSitemapPage } from './sitemap-filter.mjs';

const normalizeBasePath = (value) => {
  const raw = String(value || '/__ssr-staging').trim();
  if (!raw || raw === '/') return '/';
  return `/${raw.replace(/^\/+|\/+$/g, '')}`;
};

const runtimeBasePath = normalizeBasePath(
  process.env.SSR_BASE_PATH || process.env.SSR_STAGING_BASE_PATH,
);
process.env.SSR_RUNTIME_FRESHNESS = process.env.SSR_RUNTIME_FRESHNESS || 'true';

// Separate Astro Node runtime config for staging/shadow validation.
// Keep web/astro.config.mjs and npm run build static until a production cutover is approved.
export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || 'https://mvn.by',
  base: runtimeBasePath,
  integrations: [vue(), mdx(), tailwind(), sitemap({ filter: shouldIncludeSitemapPage })],
  output: 'server',
  adapter: node({ mode: 'standalone' }),
});
