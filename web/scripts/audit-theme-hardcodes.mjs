import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_ROOT = path.join(WEB_ROOT, 'src');
const TOKEN_SOURCE = path.join(SOURCE_ROOT, 'assets', 'index.css');
const SOURCE_EXTENSIONS = new Set(['.astro', '.css', '.scss', '.vue']);
const HARDCODE_PATTERN = /rgba\(255,\s*255,\s*255|rgba\(245,\s*253,\s*250|#fff\b|#ffffff\b|linear-gradient\([^)]*#0f8f8d[^)]*#3aa56e|linear-gradient\([^)]*#0a8e8c[^)]*#2b6eb3/i;

async function collectSourceFiles(directory, files = []) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await collectSourceFiles(target, files);
    } else if (SOURCE_EXTENSIONS.has(path.extname(entry.name)) && target !== TOKEN_SOURCE) {
      files.push(target);
    }
  }
  return files;
}

console.log('Theme hardcode audit (src)');
console.log('Allowed token source: src/assets/index.css');

const violations = [];
for (const file of await collectSourceFiles(SOURCE_ROOT)) {
  const content = await readFile(file, 'utf8');
  for (const [index, line] of content.split('\n').entries()) {
    if (HARDCODE_PATTERN.test(line)) {
      violations.push(`${path.relative(WEB_ROOT, file)}:${index + 1}:${line.trim()}`);
    }
  }
}

if (violations.length > 0) {
  for (const violation of violations) console.error(violation);
  console.error('Theme hardcodes found. Replace them with --panel-* tokens.');
  process.exit(1);
}

console.log('theme_audit=passed');
