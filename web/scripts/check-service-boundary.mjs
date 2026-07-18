import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TEXT_EXTENSIONS = new Set([
  '.astro',
  '.cjs',
  '.css',
  '.js',
  '.json',
  '.mjs',
  '.scss',
  '.ts',
  '.vue',
]);
const SCAN_ROOTS = [
  'src',
  'scripts',
  'tests',
  'astro.config.mjs',
  'astro.config.ssr.mjs',
  'build_with_prod_data.sh',
  'Dockerfile',
  'Dockerfile.prod',
  'package.json',
  'postcss.config.cjs',
  'sitemap-filter.mjs',
  'tailwind.config.mjs',
];
const IGNORED_DIRECTORIES = new Set(['.astro', 'dist', 'node_modules']);
const FORBIDDEN_RUNTIME_KEYS = [
  'BOT_TOKEN',
  'DATABASE_URL',
  'GOOGLE_APPLICATION_CREDENTIALS',
  'POSTGRES_PASSWORD',
  'R2_SECRET_ACCESS_KEY',
  'SECRET_KEY',
];
const ALLOWED_ENVIRONMENT_KEYS = new Set([
  'INTERNAL_API_URL',
  'PUBLIC_API_URL',
  'PUBLIC_GTM_ID',
  'PUBLIC_SITE_URL',
  'SSR',
  'SSR_BASE_PATH',
  'SSR_RUNTIME_DATA_CACHE_MAX_ENTRIES',
  'SSR_RUNTIME_DATA_CACHE_TTL_MS',
  'SSR_RUNTIME_FRESHNESS',
  'SSR_RUNTIME_FRESHNESS_FALLBACK_TTL_MS',
  'SSR_RUNTIME_REVISION_TIMEOUT_MS',
  'SSR_SMOKE_API_URL',
  'SSR_SMOKE_BASE_URL',
  'SSR_SMOKE_BASIC_AUTH',
  'SSR_SMOKE_BRAND_PATH',
  'SSR_SMOKE_EXPECT_CATALOG_PRODUCT_PATH',
  'SSR_SMOKE_PRODUCT_PATH',
  'SSR_SMOKE_UNPUBLISHED_PRODUCT_PATH',
  'SSR_STAGING_BASE_PATH',
]);
const ENVIRONMENT_ACCESS_PATTERN = /(?:import\.meta|process)\.env\.([A-Z][A-Z0-9_]*)/g;
const RELATIVE_IMPORT_PATTERN = /(?:import|export)\s+(?:[^'";]*?\s+from\s+)?['"](\.\.?\/[^'"]+)['"]|import\(\s*['"](\.\.?\/[^'"]+)['"]\s*\)/g;

async function collectFiles(target, files = []) {
  const absoluteTarget = path.join(WEB_ROOT, target);
  const entries = await readdir(absoluteTarget, { withFileTypes: true }).catch((error) => {
    if (error.code === 'ENOTDIR') {
      files.push(absoluteTarget);
      return null;
    }
    throw error;
  });

  if (!entries) return files;
  for (const entry of entries) {
    if (entry.isDirectory() && IGNORED_DIRECTORIES.has(entry.name)) continue;
    const child = path.join(target, entry.name);
    if (entry.isDirectory()) {
      await collectFiles(child, files);
    } else if (TEXT_EXTENSIONS.has(path.extname(entry.name))) {
      files.push(path.join(WEB_ROOT, child));
    }
  }
  return files;
}

function isInsideWebRoot(candidate) {
  const relative = path.relative(WEB_ROOT, candidate);
  return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

function lineNumber(content, offset) {
  return content.slice(0, offset).split('\n').length;
}

const files = [];
for (const target of SCAN_ROOTS) await collectFiles(target, files);

const violations = [];
for (const file of files) {
  const relativeFile = path.relative(WEB_ROOT, file);
  const content = await readFile(file, 'utf8');

  if (relativeFile !== 'scripts/check-service-boundary.mjs') {
    for (const key of FORBIDDEN_RUNTIME_KEYS) {
      const pattern = new RegExp(`\\b${key}\\b`, 'g');
      for (const match of content.matchAll(pattern)) {
        violations.push(`${relativeFile}:${lineNumber(content, match.index)} uses forbidden runtime key ${key}`);
      }
    }

    for (const match of content.matchAll(ENVIRONMENT_ACCESS_PATTERN)) {
      if (!ALLOWED_ENVIRONMENT_KEYS.has(match[1])) {
        violations.push(`${relativeFile}:${lineNumber(content, match.index)} uses undeclared environment key ${match[1]}`);
      }
    }
  }

  for (const match of content.matchAll(RELATIVE_IMPORT_PATTERN)) {
    const specifier = match[1] || match[2];
    const resolved = path.resolve(path.dirname(file), specifier);
    if (!isInsideWebRoot(resolved)) {
      violations.push(`${relativeFile}:${lineNumber(content, match.index)} imports outside web/: ${specifier}`);
    }
  }
}

const packageJson = JSON.parse(await readFile(path.join(WEB_ROOT, 'package.json'), 'utf8'));
for (const [name, command] of Object.entries(packageJson.scripts || {})) {
  if (/(^|[\s=])\.\.\//.test(command)) {
    violations.push(`package.json script ${name} reaches outside web/: ${command}`);
  }
}

if (violations.length > 0) {
  console.error('Web service boundary violations:');
  for (const violation of violations) console.error(`- ${violation}`);
  process.exit(1);
}

console.log(`web_boundary_ok files=${files.length}`);
