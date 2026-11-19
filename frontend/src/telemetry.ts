import type { Metric, RegisterValue } from './api'

/** 1012 selects a mode; 2012 reports operation and uses a different enum. */
export function heatpumpState(mode: RegisterValue | null, run: RegisterValue | null, power: Metric, now = Date.now()) {
  const usable = (row: Metric) => row != null && row.quality !== 'stale' && Number.isFinite(Date.parse(row.timestamp)) && now - Date.parse(row.timestamp) <= 300000
  const raw = (row: RegisterValue | null, labels: string[]) => {
    if (!usable(row)) return -1
    if (row!.raw != null) return row!.raw
    const text = String(row!.value)
    return /^\d+$/.test(text) ? Number(text) : labels.indexOf(text)
  }
  const setMode = raw(mode, ['Warmwasser', 'Heizen', 'Kühlen', 'Warmwasser + Heizen', 'Warmwasser + Kühlen'])
  const running = raw(run, ['Kühlen', 'Heizen', 'Abtauen', 'Sterilisieren', 'Warmwasser'])
  const off = usable(power) && ['Aus', '0', 'OFF'].includes(String(power!.value)) && Date.parse(power!.timestamp) >= Math.max(Date.parse(run?.timestamp || '') || 0, Date.parse(mode?.timestamp || '') || 0)
  const selected = setMode >= 0 && setMode <= 4 ? setMode : running === 0 ? 2 : running === 1 ? 1 : running === 4 ? 0 : -1
  const active = !off && selected >= 0
  return {
    defrost: !off && running === 2,
    heating: active && [1, 3].includes(selected),
    cooling: active && [2, 4].includes(selected),
    water: active && [0, 3, 4].includes(selected),
    label: active ? ['Warmwasser', 'Heizen', 'Kühlen', 'Heizen + Warmwasser', 'Kühlen + Warmwasser'][selected] : '',
  }
}

/** Animation follows usable operating values, independently of unrelated missing metrics. */
export function fanIsRunning(power: Metric, compressor: Metric, fans: Metric[], now = Date.now()) {
  const usable = (row: Metric) => row != null && row.quality !== 'stale' &&
    ['fresh', 'observed', 'cached'].includes(row.quality) &&
    Number.isFinite(Date.parse(row.timestamp)) && now - Date.parse(row.timestamp) <= 300000
  const speeds = fans.filter(usable).map(row => Number(row!.value)).filter(Number.isFinite)
  if (speeds.length) return speeds.some(speed => speed > 0)
  if (usable(compressor) && Number(compressor!.value) > 0) return true
  return usable(power) && ['Ein', '1', 'ON'].includes(String(power!.value))
}
