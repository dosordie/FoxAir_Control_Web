import type { TimerM1 } from './api'

export function inM1Window(timer: TimerM1 | null, now: Date): boolean {
  if (!timer?.enabled || timer.stale || !timer.window) return false

  const { start, end, days } = timer.window
  const day = (now.getDay() + 6) % 7
  const todaySelected = Boolean(days & (1 << day))
  const minute = now.getHours() * 60 + now.getMinutes()

  if (start < end) return todaySelected && minute >= start && minute < end
  const yesterdaySelected = Boolean(days & (1 << ((day + 6) % 7)))
  return (todaySelected && minute >= start) || (yesterdaySelected && minute < end)
}
