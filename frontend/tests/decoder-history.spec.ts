import { createApp, nextTick } from 'vue'
import { expect, it, vi } from 'vitest'
import { api, type CloudRow, type Register, type RegisterValue } from '../src/api'
import RegisterDecoder from '../src/components/RegisterDecoder.vue'
import HistoryChart from '../src/components/HistoryChart.vue'

it('decodes active-low contacts, active-high SG inputs and missing load outputs', async () => {
  vi.spyOn(api, 'registers').mockResolvedValue({
    catalog_size: 3,
    items: [
      { register: 2018, name: 'Tankheizer' },
      { register: 2019, bit_map: { '0': 'Kompressor', '1': 'Reserviert' } },
      { register: 2034, bit_map: { '0': 'Hochdruckschalter', '12': 'SG Kontakt 1' } },
    ] as Register[],
  })
  const root = document.createElement('div')
  const valueFor = (register: number): RegisterValue | null => {
    if (register !== 2034) return null
    return {
      register, raw: 4096, value: 4096, unit: '', transport: 'warmlink_raw', quality: 'observed',
      timestamp: '2026-11-24T09:00:00Z',
    }
  }
  const app = createApp(RegisterDecoder, { transport: 'warmlink_raw', valueFor })
  app.mount(root)
  try {
    await vi.waitFor(() => expect(root.textContent).toContain('Hochdruckschalter'))
    const rows = Object.fromEntries([...root.querySelectorAll('tbody tr')].map(row => [
      row.querySelector('th')?.textContent, row.querySelector('td:last-child')?.textContent,
    ]))
    const contacts = root.querySelector<HTMLButtonElement>('#decoder-tab-1')!
    contacts.click()
    await nextTick()
    expect(contacts.getAttribute('aria-selected')).toBe('true')
    expect(rows).toEqual({ 'Kompressor läuft': 'Unbekannt', 'Elektrischer Wassertankheizer': 'Unbekannt', Hochdruckschalter: 'Ein', 'SG Kontakt 1': 'Ein' })
  } finally {
    app.unmount()
    vi.restoreAllMocks()
  }
})

it('shows the chart tooltip and the existing value below on keyboard navigation', async () => {
  const root = document.createElement('div')
  const app = createApp(HistoryChart, {
    label: 'Austritt', unit: '°C', points: [
      { time: '2026-11-24T09:00:00Z', value: 30 },
      { time: '2026-11-24T09:05:00Z', value: 31.5 },
    ],
  })
  app.mount(root)
  try {
    const chart = root.querySelector('svg')!
    chart.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    chart.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    await nextTick()
    expect(root.querySelector('.history-tooltip')?.textContent).toContain('31,5 °C')
    expect(root.querySelector('[role="status"]')?.textContent).toContain('31,5 °C')
    chart.dispatchEvent(new Event('blur'))
    await nextTick()
    expect(root.querySelector('.history-tooltip')).toBeNull()
    expect(root.querySelector('[role="status"]')?.textContent).toContain('31,5 °C')
  } finally {
    app.unmount()
  }
})


it.each(['0011110000000000', '15360'])('decodes cloud contacts from %s', async (contacts) => {
  vi.spyOn(api, 'registers').mockResolvedValue({
    catalog_size: 2,
    items: [
      { register: 2019, bit_map: { '0': 'Kompressor', '10': '011 Alarm (0=AUS/1=EIN)' } },
      { register: 2034, bit_map: { '0': 'Hochdruckschalter', '12': 'SG Kontakt 1', '13': 'SG Kontakt 2' } },
    ] as Register[],
  })
  const root = document.createElement('div')
  const app = createApp(RegisterDecoder, {
    transport: 'cloud', valueFor: () => null,
    cloudRows: [
      { register: 2019, code: 'O01~023', value: '0000010000000001', confidence: 'confirmed' },
      { register: 2034, code: 'S01~S10', value: contacts, confidence: 'confirmed' },
    ] as CloudRow[],
  })
  app.mount(root)
  try {
    await vi.waitFor(() => expect(root.textContent).toContain('Hochdruckschalter'))
    const rows = Object.fromEntries([...root.querySelectorAll('tbody tr')].map(row => [
      row.querySelector('th')?.textContent, row.querySelector('td:last-child')?.textContent,
    ]))
    expect(rows).toEqual({ 'Kompressor läuft': 'Ein', Alarm: 'Ein', Hochdruckschalter: 'Ein', 'SG Kontakt 1': 'Ein', 'SG Kontakt 2': 'Ein' })
  } finally {
    app.unmount()
    vi.restoreAllMocks()
  }
})

it('connects sparse local samples but leaves multi-hour gaps open', () => {
  const root = document.createElement('div')
  const app = createApp(HistoryChart, {
    label: 'Außen', unit: '°C', maxGapSeconds: 3600,
    points: [
      { time: '2026-11-24T09:00:00Z', value: 2 },
      { time: '2026-11-24T09:30:00Z', value: 3 },
      { time: '2026-11-24T13:00:00Z', value: 5 },
      { time: '2026-11-24T13:15:00Z', value: 6 },
    ],
  })
  app.mount(root)
  try {
    const line = root.querySelector('path[stroke="#d76b21"]')
    expect(line?.getAttribute('d')?.match(/[ML]/g)).toEqual(['M', 'L', 'M', 'L'])
  } finally {
    app.unmount()
  }
})
