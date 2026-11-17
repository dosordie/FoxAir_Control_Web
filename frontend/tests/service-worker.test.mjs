import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { test } from 'node:test'
import vm from 'node:vm'

const source = (await readFile(new URL('../scripts/service-worker.template.js', import.meta.url), 'utf8'))
  .replace('__VERSION__', 'test')
  .replace('__PRECACHE__', JSON.stringify(['/index.html', '/assets/app.js']))

function worker(fetch = async () => { throw new Error('offline') }) {
  const handlers = {}
  const stored = new Map([['/index.html', new Response('<html>FoxAir offline shell</html>')]])
  const key = request => typeof request === 'string' ? request : new URL(request.url).pathname
  const cache = {
    match: async request => stored.get(key(request))?.clone(),
    put: async (request, response) => stored.set(key(request), response),
    addAll: async () => {},
  }
  vm.runInNewContext(source, {
    self: { location: { origin: 'https://foxair.test' }, clients: { claim: async () => {} },
      addEventListener: (name, callback) => { handlers[name] = callback } },
    caches: { open: async () => cache }, URL, Request, Response, fetch,
  })
  return handlers
}

test('API, writes and cross-origin traffic are never intercepted or queued', () => {
  const handlers = worker()
  for (const [url, method] of [
    ['https://foxair.test/api/dashboard', 'GET'],
    ['https://foxair.test/api/parameters/1158/write', 'POST'],
    ['https://foxair.test/', 'POST'],
    ['https://other.test/assets/app.js', 'GET'],
  ]) {
    let intercepted = false
    handlers.fetch({ request: { url, method, mode: 'cors' }, respondWith: () => { intercepted = true } })
    assert.equal(intercepted, false, `${method} ${url}`)
  }
})

test('an offline navigation opens only the cached public application shell', async () => {
  const handlers = worker()
  let response
  handlers.fetch({ request: { url: 'https://foxair.test/', method: 'GET', mode: 'navigate' },
    respondWith: pending => { response = pending } })
  assert.match(await (await response).text(), /FoxAir offline shell/)
})

test('a successful navigation uses and refreshes the online HTML', async () => {
  const handlers = worker(async () => new Response('<html>new version</html>', {headers:{'content-type':'text/html'}}))
  let response
  handlers.fetch({ request: { url: 'https://foxair.test/', method: 'GET', mode: 'navigate' },
    respondWith: pending => { response = pending } })
  assert.match(await (await response).text(), /new version/)
})
