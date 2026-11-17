import { createHash } from 'node:crypto'
import { readFile, readdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const dist = new URL('../dist/', import.meta.url)
async function list(directory, prefix = '') {
  const result = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const name = prefix + entry.name
    if (entry.isDirectory()) result.push(...await list(new URL(entry.name + '/', directory), name + '/'))
    else if (name !== 'cloud_catalog.json' && !name.startsWith('.')) result.push(name)
  }
  return result.sort()
}
const files = await list(dist)
const hash = createHash('sha256')
for (const file of files) hash.update(await readFile(new URL(file, dist)))
const source = await readFile(new URL('./service-worker.template.js', import.meta.url), 'utf8')
await writeFile(new URL('sw.js', dist), source
  .replace('__VERSION__', hash.digest('hex').slice(0, 16))
  .replace('__PRECACHE__', JSON.stringify(files.map(file => '/' + file))))
console.log('Offline shell generated:', fileURLToPath(new URL('sw.js', dist)))
