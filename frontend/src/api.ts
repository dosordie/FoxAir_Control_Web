export type TransportId = 'cloud' | 'standard_modbus' | 'display_modbus' | 'warmlink_raw'
export type Metric = { value: number | string; unit: string; raw: number; quality: string; timestamp: string } | null
export type Dashboard = {
  transport: TransportId
  status: 'online' | 'partial' | 'unavailable'
  timestamp: string
  error: string | null
  metrics: Record<'power' | 'mode' | 'flow' | 'tank' | 'outdoor' | 'return' | 'supply' | 'target', Metric>
  live_supported: boolean
}
export type Transport = { id: TransportId; name: string; configured: boolean; read_supported: boolean; reason: string }
export type Register = {
  register: number
  code: string
  name: string
  description: string
  unit: string
  type: string
  mode: string
  write_available: boolean
}
export type RegisterValue = { register: number; raw: number; value: string | number; unit: string; transport: string; timestamp: string; quality: string }

async function get<T>(path: string): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 12000)
  try {
    const response = await fetch(path, { signal: controller.signal, headers: { Accept: 'application/json' }, cache: 'no-store' })
    if (!response.ok) {
      const body = await response.json().catch(() => ({})) as { detail?: string }
      throw new Error(body.detail || 'HTTP ' + response.status)
    }
    return await response.json() as T
  } finally {
    clearTimeout(timer)
  }
}
export const api = {
  health: () => get<{ ok: boolean; version: string }>('/api/health'),
  transports: () => get<{ items: Transport[]; live_supported: boolean }>('/api/transports'),
  dashboard: (transport: TransportId) => get<Dashboard>('/api/dashboard?transport=' + encodeURIComponent(transport)),
  registers: (query: string) => get<{ items: Register[]; catalog_size: number }>('/api/registers?query=' + encodeURIComponent(query)),
  read: (register: number, transport: TransportId) =>
    get<RegisterValue>('/api/registers/' + register + '/read?transport=' + encodeURIComponent(transport)),
}
