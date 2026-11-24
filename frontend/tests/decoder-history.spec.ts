import { createApp, nextTick } from 'vue'
import { expect, it, vi } from 'vitest'
import { api, type Register, type RegisterValue } from '../src/api'
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
    const rows = Object.fromEntries([...root.querySelectorAll('dl > div')].map(row => [
      row.querySelector('dt')?.textContent, row.querySelector('dd')?.textContent,
    ]))
    expect(rows).toEqual({ Kompressor: 'Unbekannt', Tankheizer: 'Unbekannt', Hochdruckschalter: 'Ein', 'SG Kontakt 1': 'Ein' })
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
