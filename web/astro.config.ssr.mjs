import { defineConfig } from 'astro/config';
import vue from '@astrojs/vue';
import mdx from '@astrojs/mdx';
import tailwind from '@astrojs/tailwind';
import sitemap from '@astrojs/sitemap';
import node from '@astrojs/node';

const normalizeBasePath = (value) => {
  const raw = String(value || '/__ssr-staging').trim();
  if (!raw || raw === '/') return '/';
  return `/${raw.replace(/^\/+|\/+$/g, '')}`;
};

const stagingBasePath = normalizeBasePath(process.env.SSR_STAGING_BASE_PATH);

// Staging-only Astro Node runtime config for issue #464.
// Keep web/astro.config.mjs and npm run build static until a production cutover is approved.
export default defineConfig({
  site: process.env.PUBLIC_SITE_URL || 'https://mvn.by',
  base: stagingBasePath,
  integrations: [vue(), mdx(), tailwind(), sitemap()],
  output: 'server',
  adapter: node({ mode: 'standalone' }),
});
