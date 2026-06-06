const EXCLUDED_SITEMAP_PATHS = new Set([
  '/404/',
  '/cart/',
  '/checkout/',
  '/success/',
]);

export function shouldIncludeSitemapPage(page) {
  const { pathname } = new URL(page);
  if (EXCLUDED_SITEMAP_PATHS.has(pathname)) return false;
  if (pathname === '/index.php' || pathname.startsWith('/index.php/')) return false;
  return true;
}
