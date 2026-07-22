import { readFile, readdir } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';

const root = new URL('../src/', import.meta.url);
const allowedExtensions = new Set(['.ts', '.tsx', '.js', '.jsx', '.vue']);
const nativeDialogPattern = /(?:\bwindow\s*\.\s*)?\b(?:alert|confirm|prompt)\s*\(/g;
const findings = [];

const walk = async (directory) => {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await walk(path);
      continue;
    }
    if (!allowedExtensions.has(extname(entry.name))) continue;
    const content = await readFile(path, 'utf8');
    for (const match of content.matchAll(nativeDialogPattern)) {
      const line = content.slice(0, match.index).split('\n').length;
      findings.push(`${relative(root.pathname, path)}:${line}: ${match[0]}`);
    }
  }
};

await walk(root.pathname);

if (findings.length) {
  console.error('Native browser dialogs are forbidden in manager_frontend/src:');
  findings.forEach((finding) => console.error(`- ${finding}`));
  process.exit(1);
}

console.log('Native browser dialog audit passed');
