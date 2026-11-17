import type { Metric } from './api'

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
