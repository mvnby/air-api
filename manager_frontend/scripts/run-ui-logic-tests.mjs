import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'vite';

const outputDirectory = await mkdtemp(join(tmpdir(), 'mvn-manager-ui-tests-'));

try {
  await build({
    configFile: false,
    logLevel: 'silent',
    build: {
      emptyOutDir: true,
      outDir: outputDirectory,
      lib: {
        entry: new URL('../tests/ui-logic.test.ts', import.meta.url).pathname,
        formats: ['es'],
        fileName: 'ui-logic.test',
      },
    },
  });
  await import(pathToFileURL(join(outputDirectory, 'ui-logic.test.js')).href);
} finally {
  await rm(outputDirectory, { recursive: true, force: true });
}
