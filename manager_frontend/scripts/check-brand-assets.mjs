import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// Production mounts only /manager/assets as static files; other /manager URLs
// are SPA navigation routes. Vite's dev server also serves public-root files,
// so dev screenshots alone cannot catch this deployment contract regression.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = await readFile(path.join(root, 'dist/index.html'), 'utf8');
const favicon = html.match(/<link\s+rel="icon"[^>]*href="([^"]+)"/)?.[1];
assert.equal(favicon, '/manager/assets/kitlane-mark.svg');
for (const file of ['kitlane-mark.svg', 'kitlane-mark-mono.svg']) {
  const built = await readFile(path.join(root, 'dist/assets', file), 'utf8');
  const source = await readFile(path.join(root, 'public/assets', file), 'utf8');
  assert.equal(built, source);
  assert.match(built, /^<svg\s/);
}
const entry = html.match(/<script[^>]*src="\/manager\/assets\/([^"/]+\.js)"/)?.[1];
assert(entry, 'Built Manager entry must use the production static mount');
const bundle = await readFile(path.join(root, 'dist/assets', entry), 'utf8');
assert(bundle.includes('/manager/assets/kitlane-mark.svg'), 'Platform mark must use the production static mount');
console.log('Manager production brand assets passed');
