import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const manifest = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
const source = await readFile(join(root, 'src', 'client', 'index.js'), 'utf8');
const host = await readFile(join(root, 'src', 'index.js'), 'utf8');
const output = [
  `window.__ModuleLoader__.load({ id: ${JSON.stringify(manifest.name)}, factory: (require) => {`,
  'var module = { exports: {} }; var exports = module.exports;',
  source,
  'return module.exports; } });',
  ''
].join('\n');

await mkdir(join(root, 'lib'), { recursive: true });
await writeFile(join(root, 'lib', 'client.js'), output);
await writeFile(join(root, 'lib', 'index.js'), host);
await rm(join(root, '.client-build'), { recursive: true, force: true });
console.log(`built lib/client.js (${output.length} bytes)`);
