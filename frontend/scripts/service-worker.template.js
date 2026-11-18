// Only public application files are cached. API traffic and writes are network-only.
const PREFIX = 'foxair-shell-'
const CACHE = PREFIX + '__VERSION__'
const PRECACHE = __PRECACHE__

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(
    PRECACHE.map(url => new Request(url, { cache: 'reload', credentials: 'same-origin' })),
  )))
  // New versions wait for existing tabs to close; never force a reload during editing.
})
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith(PREFIX) && key !== CACHE) await caches.delete(key)
    }
    await self.clients.claim()
  })())
})
self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin ||
      url.pathname === '/api' || url.pathname.startsWith('/api/')) return
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      const cache = await caches.open(CACHE)
      const cached = await cache.match('/index.html')
      const network = (async () => {
        try {
          const response = await fetch(request)
          if (response.ok && response.headers.get('content-type')?.includes('text/html')) {
            await cache.put('/index.html', response.clone())
          }
          return response
        } catch {
          return cached || Response.error()
        }
      })()
      // Keep updating in the background if a slow connection delays startup.
      event.waitUntil(network.then(() => {}))
      if (!cached) return network
      let timer
      try {
        return await Promise.race([network, new Promise(resolve => {
          timer = setTimeout(() => resolve(cached), 1500)
        })])
      } finally { clearTimeout(timer) }
    })())
    return
  }
  if (!PRECACHE.includes(url.pathname) && !url.pathname.startsWith('/assets/')) return
  event.respondWith((async () => {
    const cache = await caches.open(CACHE)
    const cached = await cache.match(request)
    if (cached) return cached
    const response = await fetch(request)
    if (response.ok && response.type === 'basic') await cache.put(request, response.clone())
    return response
  })())
})
