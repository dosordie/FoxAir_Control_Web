export type TransportId = 'cloud' | 'standard_modbus' | 'display_modbus' | 'warmlink_raw'
export type Metric = { value: number | string; unit: string; raw: number | null; quality: string; timestamp: string; source_code?: string; label?: string } | null
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
  group: string
  name: string
  description: string
  unit: string
  type: string
  mode: string
  write_available: boolean
  cloud?: {code:string;value:string|number;unit:string;timestamp:string;quality:string}|null
}
export type RegisterValue = { register: number; raw: number | null; value: string | number; unit: string; transport: string; timestamp: string; quality: string }

export type CloudConfigStatus = {
  configured: boolean
  username_configured: boolean
  password_configured: boolean
  device_configured: boolean
  storage: string
  admin_enabled: boolean
}
export type CloudRow = {
  code: string
  name: string
  register: number | null
  group: string
  kind: string
  unit: string
  confidence: string
  value: string | number | null
  timestamp: string | null
  quality: string
  supported: boolean
}
export type CloudValues = {
  items: CloudRow[]
  total: number
  supported: number
  status: string
  progress: number
  last_scan: number
  error: string | null
}
export type CloudLog = {time: string; kind: string; message: string; count?: number}
export type CloudAccount = {username: string; device_code: string}

export type CloudDevice = {
  deviceCode: string
  deviceNickName?: string
  deviceName?: string
  model?: string
  custModel?: string
  deviceStatus?: string | number
  isFault?: boolean
  dtuSoftwareVer?: string
  dtuSignalIntensity?: number | string
  isShared?: boolean
  houseName?: string
  houseRoleType?: string
}

async function post<T>(path: string, body: object): Promise<T> {
  const response = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body), cache: 'no-store', credentials: 'same-origin'
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(data.detail || 'HTTP ' + response.status)
  }
  return await response.json() as T
}

async function get<T>(path: string): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), path.startsWith('/api/dashboard') ? 55000 : 15000)
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
  dashboard: (transport: TransportId, live = false) => get<Dashboard>('/api/dashboard?transport=' + encodeURIComponent(transport) + (live ? '&live=true' : '')),
  registerGroups: () => get<{ items: { group: string; count: number }[] }>('/api/register-groups'),
  registers: (query: string, group = '') => get<{ items: Register[]; catalog_size: number }>('/api/registers?query=' + encodeURIComponent(query) + '&group=' + encodeURIComponent(group) + '&limit=200'),
  cloudStatus: () => get<CloudConfigStatus>('/api/cloud/config'),
  cloudSave: (admin_password: string, username: string, password: string, device_code: string) =>
    post<CloudConfigStatus>('/api/cloud/config', { admin_password, username, password, device_code }),
  cloudDevices: (admin_password: string) =>
    post<{ items: CloudDevice[]; count: number }>('/api/cloud/devices', { admin_password }),
  cloudDeviceStatus: (admin_password: string) =>
    post<{ status: Record<string, string | number | boolean | null> }>('/api/cloud/device-status', { admin_password }),
  cloudAccount: (admin_password: string) =>
    post<CloudAccount>('/api/cloud/account', { admin_password }),
  cloudLogs: () => get<{ items: CloudLog[] }>('/api/cloud/logs'),
  cloudValues: () => get<CloudValues>('/api/cloud/values'),
  cloudScan: (admin_password: string) =>
    post<{ started: boolean; reason?: string; count?: number }>('/api/cloud/scan', { admin_password }),
  read: (register: number, transport: TransportId) =>
    get<RegisterValue>('/api/registers/' + register + '/read?transport=' + encodeURIComponent(transport)),
}
