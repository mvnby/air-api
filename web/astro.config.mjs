import { defineConfig } from 'astro/config';
import vue from '@astrojs/vue';
import mdx from '@astrojs/mdx';
import tailwind from '@astrojs/tailwind';
import sitemap from '@astrojs/sitemap';
import { shouldIncludeSitemapPage } from './sitemap-filter.mjs';

// https://astro.build/config
export default defineConfig({
  site: 'https://mvn.by',
  integrations: [vue(), mdx(), tailwind(), sitemap({ filter: shouldIncludeSitemapPage })],
  output: 'static'
});
