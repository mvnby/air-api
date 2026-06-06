#!/usr/bin/env node

import crypto from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(__dirname, '..');
const publicRoot = path.join(webRoot, 'public');
const publicImageRoot = path.join(publicRoot, 'img');

const SUPPORTED_INPUT_EXTENSIONS = new Set([
  '.avif',
  '.gif',
  '.jpeg',
  '.jpg',
  '.png',
  '.tif',
  '.tiff',
  '.webp',
]);
const AUDIT_EXTENSIONS = new Set(['.avif', '.jpeg', '.jpg', '.png', '.webp']);

function usage() {
  console.log(`Content image optimizer

Usage:
  npm run image:content -- optimize --input <path> --namespace <blog|service|hero|brand> [options]
  npm run image:audit -- [options]

Optimize options:
  --input <path>          Source image file.
  --namespace <name>      Output namespace under web/public/img.
  --slug <slug>           Output file basename. Defaults to the input basename.
  --name <slug>           Alias for --slug.
  --max-width <px>        Resize box width. Default: 1600.
  --max-height <px>       Resize box height. Default: 1200.
  --quality <1-100>       WebP quality. Default: 82.
  --avif                 Also write an AVIF variant.
  --avif-quality <1-100>  AVIF quality. Default: 55.
  --hash                 Append an 8-character output content hash to the filename.
  --dry-run              Process and print output stats without writing files.
  --overwrite            Replace an existing output file.

Audit options:
  --root <path>           Directory to scan. Default: web/public.
  --max-size-kb <kb>      Warn for PNG/JPEG above this size. Default: 500.
  --max-webp-kb <kb>      Warn for WebP/AVIF above this size. Default: 350.
  --max-edge <px>         Warn when width or height exceeds this. Default: 2400.
  --limit <n>             Number of detailed rows to print. Default: 30.
  --fail-on-issues       Exit non-zero when warnings are found.

Content assets are committed storefront files. Product uploads and product
variants still belong to the backend media/R2 pipeline.`);
}

function parseArgs(argv) {
  const args = {
    _: [],
    avif: false,
    dryRun: false,
    failOnIssues: false,
    hash: false,
    overwrite: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) {
      args._.push(token);
      continue;
    }

    const [rawKey, inlineValue] = token.slice(2).split('=', 2);
    const key = rawKey.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    if (['avif', 'dryRun', 'failOnIssues', 'hash', 'help', 'overwrite'].includes(key)) {
      args[key] = true;
      continue;
    }

    const value = inlineValue ?? argv[index + 1];
    if (value === undefined || value.startsWith('--')) {
      throw new Error(`Missing value for --${rawKey}`);
    }
    args[key] = value;
    if (inlineValue === undefined) index += 1;
  }

  if (args.name && !args.slug) {
    args.slug = args.name;
  }

  return args;
}

function intOption(args, key, fallback, { min = 1, max = Number.MAX_SAFE_INTEGER } = {}) {
  const raw = args[key];
  if (raw === undefined) return fallback;
  const value = Number.parseInt(String(raw), 10);
  if (!Number.isFinite(value) || value < min || value > max) {
    throw new Error(`--${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)} must be between ${min} and ${max}`);
  }
  return value;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb >= 100 ? 0 : 1)} KB`;
  return `${(kb / 1024).toFixed(2)} MB`;
}

function sanitizeSegment(value, label) {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '');

  if (!normalized) {
    throw new Error(`${label} is empty after sanitizing`);
  }

  if (normalized === '.' || normalized === '..' || normalized.includes('..')) {
    throw new Error(`${label} contains an unsafe path segment`);
  }

  return normalized;
}

function publicRefFor(filePath) {
  return `/${path.relative(publicRoot, filePath).split(path.sep).join('/')}`;
}

async function pathExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function writeOutput(filePath, content, { dryRun, overwrite }) {
  if (dryRun) return;
  if (!overwrite && await pathExists(filePath)) {
    throw new Error(`${publicRefFor(filePath)} already exists. Pass --overwrite or choose another --slug.`);
  }
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, content);
}

async function optimize(args) {
  if (!args.input) {
    throw new Error('optimize requires --input');
  }
  if (!args.namespace) {
    throw new Error('optimize requires --namespace');
  }

  const inputPath = path.resolve(process.cwd(), args.input);
  const inputExt = path.extname(inputPath).toLowerCase();
  if (!SUPPORTED_INPUT_EXTENSIONS.has(inputExt)) {
    throw new Error(`Unsupported input extension: ${inputExt || '(none)'}`);
  }

  const namespace = sanitizeSegment(args.namespace, 'namespace');
  const slug = sanitizeSegment(args.slug || path.basename(inputPath, inputExt), 'slug');
  const maxWidth = intOption(args, 'maxWidth', 1600, { min: 16, max: 12000 });
  const maxHeight = intOption(args, 'maxHeight', 1200, { min: 16, max: 12000 });
  const quality = intOption(args, 'quality', 82, { min: 1, max: 100 });
  const avifQuality = intOption(args, 'avifQuality', 55, { min: 1, max: 100 });

  const source = sharp(inputPath, { animated: false, limitInputPixels: 50_000_000 });
  const sourceMetadata = await source.metadata();
  if (!sourceMetadata.width || !sourceMetadata.height) {
    throw new Error('Could not read input dimensions');
  }

  const basePipeline = sharp(inputPath, { animated: false, limitInputPixels: 50_000_000 })
    .rotate()
    .resize({
      width: maxWidth,
      height: maxHeight,
      fit: 'inside',
      withoutEnlargement: true,
    });

  const webpBuffer = await basePipeline.clone().webp({ quality, effort: 6 }).toBuffer();
  const webpHash = crypto.createHash('sha256').update(webpBuffer).digest('hex').slice(0, 8);
  const fileBase = args.hash ? `${slug}-${webpHash}` : slug;
  const outputDir = path.join(publicImageRoot, namespace);
  const webpPath = path.join(outputDir, `${fileBase}.webp`);

  await writeOutput(webpPath, webpBuffer, { dryRun: args.dryRun, overwrite: args.overwrite });
  const webpMetadata = await sharp(webpBuffer).metadata();

  const outputs = [
    {
      format: 'webp',
      path: webpPath,
      bytes: webpBuffer.length,
      width: webpMetadata.width,
      height: webpMetadata.height,
    },
  ];

  if (args.avif) {
    const avifBuffer = await basePipeline.clone().avif({ quality: avifQuality, effort: 6 }).toBuffer();
    const avifPath = path.join(outputDir, `${fileBase}.avif`);
    await writeOutput(avifPath, avifBuffer, { dryRun: args.dryRun, overwrite: args.overwrite });
    const avifMetadata = await sharp(avifBuffer).metadata();
    outputs.push({
      format: 'avif',
      path: avifPath,
      bytes: avifBuffer.length,
      width: avifMetadata.width,
      height: avifMetadata.height,
    });
  }

  const inputStats = await fs.stat(inputPath);
  console.log(args.dryRun ? 'Content image optimization dry run' : 'Content image optimized');
  console.log(`Input: ${path.relative(process.cwd(), inputPath)} (${sourceMetadata.width}x${sourceMetadata.height}, ${formatBytes(inputStats.size)})`);
  console.log(`Resize box: ${maxWidth}x${maxHeight}`);
  for (const output of outputs) {
    const savings = inputStats.size > 0 ? `${Math.max(0, 100 - (output.bytes / inputStats.size) * 100).toFixed(1)}% smaller` : 'n/a';
    console.log(`Output: ${publicRefFor(output.path)} (${output.width}x${output.height}, ${formatBytes(output.bytes)}, ${savings})`);
  }
}

async function walkFiles(root) {
  const entries = await fs.readdir(root, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const filePath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...await walkFiles(filePath));
    } else if (entry.isFile()) {
      files.push(filePath);
    }
  }
  return files;
}

async function audit(args) {
  const root = path.resolve(process.cwd(), args.root || publicRoot);
  const maxSizeKb = intOption(args, 'maxSizeKb', 500, { min: 1 });
  const maxWebpKb = intOption(args, 'maxWebpKb', 350, { min: 1 });
  const maxEdge = intOption(args, 'maxEdge', 2400, { min: 16 });
  const limit = intOption(args, 'limit', 30, { min: 1, max: 1000 });

  const files = (await walkFiles(root))
    .filter((filePath) => AUDIT_EXTENSIONS.has(path.extname(filePath).toLowerCase()));

  const rows = [];
  for (const filePath of files) {
    const stats = await fs.stat(filePath);
    let metadata;
    try {
      metadata = await sharp(filePath, { animated: false, limitInputPixels: 80_000_000 }).metadata();
    } catch (error) {
      rows.push({
        path: filePath,
        bytes: stats.size,
        issues: [`unreadable: ${error.message}`],
      });
      continue;
    }

    const ext = path.extname(filePath).toLowerCase();
    const sizeLimitKb = ext === '.webp' || ext === '.avif' ? maxWebpKb : maxSizeKb;
    const issues = [];
    if (stats.size > sizeLimitKb * 1024) {
      issues.push(`size>${sizeLimitKb}KB`);
    }
    if ((metadata.width || 0) > maxEdge || (metadata.height || 0) > maxEdge) {
      issues.push(`edge>${maxEdge}px`);
    }

    rows.push({
      path: filePath,
      bytes: stats.size,
      width: metadata.width,
      height: metadata.height,
      issues,
    });
  }

  const flagged = rows
    .filter((row) => row.issues.length > 0)
    .sort((left, right) => right.issues.length - left.issues.length || right.bytes - left.bytes);
  const largest = rows
    .filter((row) => row.issues.length === 0)
    .sort((left, right) => right.bytes - left.bytes)
    .slice(0, Math.max(0, limit - flagged.length));
  const details = [...flagged.slice(0, limit), ...largest].slice(0, limit);

  console.log('Content image audit report');
  console.log(`Root: ${path.relative(process.cwd(), root) || '.'}`);
  console.log(`Thresholds: PNG/JPEG>${maxSizeKb}KB, WebP/AVIF>${maxWebpKb}KB, max edge>${maxEdge}px`);
  console.log(`Scanned: ${rows.length} raster assets`);
  console.log(`Flagged: ${flagged.length}`);

  if (details.length > 0) {
    console.log('');
    console.log('Top rows:');
    for (const row of details) {
      const rel = path.relative(process.cwd(), row.path).split(path.sep).join('/');
      const dimensions = row.width && row.height ? `${row.width}x${row.height}` : 'unknown';
      const issueText = row.issues.length > 0 ? row.issues.join(', ') : 'ok';
      console.log(`- ${rel}: ${dimensions}, ${formatBytes(row.bytes)} (${issueText})`);
    }
  }

  if (flagged.length > 0 && args.failOnIssues) {
    process.exitCode = 1;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const command = args._[0] || (args.help ? 'help' : 'audit');

  if (command === 'help' || args.help) {
    usage();
    return;
  }

  if (command === 'optimize') {
    await optimize(args);
    return;
  }

  if (command === 'audit') {
    await audit(args);
    return;
  }

  throw new Error(`Unknown command: ${command}`);
}

main().catch((error) => {
  console.error(`content-images: ${error.message}`);
  process.exit(1);
});
