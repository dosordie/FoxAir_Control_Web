import { expect, it } from 'vitest'
import { inM1Window } from '../src/timerWindow'

const timer = {
  enabled: true, stale: false, max_kw: 3,
  window: { start: 6 * 60, end: 22 * 60, days: 1 }, // Monday
}
const onMonday = (hours: number, minutes = 0) => new Date(2026, 10, 23, hours, minutes)

it('uses selected days and includes the start but excludes the end', () => {
  expect(inM1Window(timer, onMonday(5, 59))).toBe(false)
  expect(inM1Window(timer, onMonday(6))).toBe(true)
  expect(inM1Window(timer, onMonday(22))).toBe(false)
  expect(inM1Window(timer, new Date(2026, 10, 24, 10))).toBe(false)
  expect(inM1Window({ ...timer, enabled: false }, onMonday(10))).toBe(false)
  expect(inM1Window({ ...timer, stale: true }, onMonday(10))).toBe(false)
  expect(inM1Window({ ...timer, window: null }, onMonday(10))).toBe(false)
})

it('carries a Sunday window through midnight into Monday', () => {
  const overnight = { ...timer, window: { start: 22 * 60, end: 6 * 60, days: 1 << 6 } }
  expect(inM1Window(overnight, new Date(2026, 10, 22, 23))).toBe(true)
  expect(inM1Window(overnight, onMonday(5, 59))).toBe(true)
  expect(inM1Window(overnight, onMonday(6))).toBe(false)
  expect(inM1Window(overnight, onMonday(23))).toBe(false)
})
