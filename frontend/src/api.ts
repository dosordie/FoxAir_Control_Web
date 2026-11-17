export type TransportId = 'cloud' | 'standard_modbus' | 'display_modbus' | 'warmlink_raw'
export type Metric = { value: number | string; unit: string; raw: number | null; quality: string; timestamp: string; source_code?: string; label?: string } | null
export type Dashboard = {
  transport: TransportId
  status: 'online' | 'partial' | 'unavailable'
  timestamp: string
  error: string | null
  device_name?: string
  metrics: Record<'power' | 'mode' | 'flow' | 'tank' | 'outdoor' | 'return' | 'supply' | 'target' | 'base_target' | 'silent' | 'compressor_frequency', Metric>
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
  value_map: Record<string,string>
  cloud?: {code:string;value:string|number;unit:string;timestamp:string;quality:string;display_value?:string|null}|null
}
export type RegisterValue = { register: number; raw: number | null; value: string | number; unit: string; transport: string; timestamp: string; quality: string;display_value?:string|null;code?:string;name?:string;group?:string }
export type LteScan = {status:'idle'|'running'|'complete'|'partial'|'error';completed:number;total:number;error:string|null}
export type ConnectionState = {connected:boolean;mode:string;error:string|null;last_rx:number|null;lease_seconds:number;pending_read?:{register:number;count:number;age_seconds:number;ambiguous:boolean}|null}
export type LteSnapshot = {values:Record<string,RegisterValue>;metrics:Partial<Dashboard['metrics']>;connection:ConnectionState;scan:LteScan;removed?:string[];reset?:boolean}

export type CloudConfigStatus = {
  configured: boolean
  username_configured: boolean
  password_configured: boolean
  device_configured: boolean
  storage: string
  admin_enabled: boolean
}
export type UpdateStatus = {
  installed: boolean
  current: string | null
  deployed: string | null
  remote: string | null
  remote_build: string | null
  build_ready: boolean
  update_available: boolean
  pending: boolean
  running: boolean
  last_result: string | null
}
export type SpecialDialog = {
  id: string
  title: string
  description: string
  codes: string[]
  count: number
  read_only: boolean
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
  display_value: string | null
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
export type CloudWriteResult = {
  status: 'confirmed' | 'unchanged' | 'rejected' | 'unconfirmed'
  confirmed: boolean
  code: string
  value?: number
  message?: string
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

export function errorMessage(body: unknown, status: number): string {
  function describe(value: unknown): string {
    if (typeof value === 'string') return value
    if (Array.isArray(value)) return value.map(describe).filter(Boolean).join('; ')
    if (value && typeof value === 'object') {
      const item = value as Record<string, unknown>
      if (item.detail) return describe(item.detail)
      if (item.msg || item.message || item.error) {
        const location = Array.isArray(item.loc) ? item.loc.filter(x => x !== 'body').join('.') : ''
        return (location ? location + ': ' : '') + describe(item.msg || item.message || item.error)
      }
    }
    return ''
  }
  return describe(body) || 'Anfrage fehlgeschlagen (HTTP ' + status + ')'
}

// Vue number inputs emit numbers even without an explicit .number modifier.
export function writeValueText(value: string | number): string {
  return String(value).trim()
}

async function post<T>(path: string, body: object): Promise<T> {
  const response = await fetch(path, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-FoxAir-Admin': '1' },
    body: JSON.stringify(body), cache: 'no-store', credentials: 'same-origin'
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(errorMessage(data, response.status))
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
      throw new Error(errorMessage(body, response.status))
    }
    return await response.json() as T
  } finally {
    clearTimeout(timer)
  }
}
export type WarmlinkConfig = {connection_mode:'on_demand'|'browser'|'permanent';host:string;port:number;enabled:boolean;slave:number}
export type TimerSnapshot = {values:Record<string,number>;transport:TransportId;kind:string}
export const api = {
  lteSnapshot:()=>get<LteSnapshot>('/api/warmlink/state'),
  lteScan:()=>post<LteScan>('/api/warmlink/scan',{}),
  cloudEnum: (key:string)=>post<{items:Record<string,string>[]}>('/api/cloud/service-enum',{key}),
  cloudInsight: (kind:'ota'|'metadata'|'ai')=>post<{checked_at:string;cached:boolean;available?:boolean;count?:number;items?:Record<string,string>[];source?:string;frequency_supported?:boolean|null;ai_enabled?:boolean|null;sg_supported?:boolean|null;sg_mode?:number|null}>('/api/cloud/insights/'+kind,{}),
  cloudHistory: (address:string,start:string,end:string,frequency:string)=>post<{checked_at:string;cached:boolean;unit:string;points:{time:string;value:number;incomplete:boolean}[]}>('/api/cloud/history',{address,start,end,frequency,time_zone:1}),
  busLease: () => post<object>('/api/warmlink/lease',{}),
  passiveDashboard: () => get<Dashboard>('/api/dashboard?transport=warmlink_raw&passive=true'),
  busConnection: () => get<{connected:boolean;mode:string;error:string|null;last_rx:number|null;lease_seconds:number;observed:Record<string,{raw:number;age_seconds:number}>}>('/api/warmlink/connection'),
  timerRead: (kind:string,transport:TransportId) => get<TimerSnapshot>('/api/timers/'+kind+'?transport='+encodeURIComponent(transport)),
  timerWrite: (kind:string,transport:TransportId,values:Record<string,number>,expected:Record<string,number>) => post<{confirmed:boolean;status:string;values?:Record<string,number>;message?:string}>('/api/timers/'+kind,{transport,values,expected}),
  warmlinkConfig: () => post<WarmlinkConfig>('/api/warmlink/config', {}),
  saveWarmlinkConfig: (config: WarmlinkConfig) => post<WarmlinkConfig>('/api/warmlink/config/save', config),
  warmlinkWrite: (code:'Power'|'Mode'|'H22'|'R02',value:string,expected:string) => post<CloudWriteResult>('/api/warmlink/write',{code,value,expected}),
  health: () => get<{ ok: boolean; version: string }>('/api/health'),
  transports: () => get<{ items: Transport[]; live_supported: boolean }>('/api/transports'),
  dashboard: (transport: TransportId, live = false) => get<Dashboard>('/api/dashboard?transport=' + encodeURIComponent(transport) + (live ? '&live=true' : '')),
  registerGroups: () => get<{ items: { group: string; count: number }[] }>('/api/register-groups'),
  registers: (query: string, group = '') => get<{ items: Register[]; catalog_size: number }>('/api/registers?query=' + encodeURIComponent(query) + '&group=' + encodeURIComponent(group) + '&limit=200'),
  adminSession: () => get<{ authenticated: boolean; role: string }>('/api/admin/session'),
  adminLogin: (admin_password: string) =>
    post<{ authenticated: boolean; role: string }>('/api/admin/login', { admin_password }),
  adminLogout: () =>
    post<{ authenticated: boolean; role: string }>('/api/admin/logout', {}),
  cloudWrite: (code: 'Power' | 'Mode' | 'H22' | 'R02', value: string, expected: string) =>
    post<CloudWriteResult>('/api/cloud/write', { code, value, expected }),
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
  updateStatus: () => get<UpdateStatus>('/api/update/status'),
  requestUpdate: (admin_password: string) =>
    post<{requested:boolean}>('/api/update/request', {admin_password}),
  specialDialogs: () => get<{items: SpecialDialog[]}>('/api/cloud/dialogs'),
  refreshSpecialDialog: (id: string) =>
    post<{updated:boolean;reason?:string;count:number;unsupported?:number}>(
      '/api/cloud/dialogs/' + encodeURIComponent(id) + '/refresh', {}
    ),
  cloudScan: (admin_password: string) =>
    post<{ started: boolean; reason?: string; count?: number }>('/api/cloud/scan', { admin_password }),
  read: (register: number, transport: TransportId) =>
    get<RegisterValue>('/api/registers/' + register + '/read?transport=' + encodeURIComponent(transport)),
}
