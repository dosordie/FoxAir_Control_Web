const numericText = /^[+-]?[0-9]+(?:[.,][0-9]+)?$/

export function isGiraText(value: string | number | null | undefined) {
  return typeof value === 'string' && !numericText.test(value.trim())
}

export function formatGiraValue(
  value: string | number | null | undefined,
  decimals?: number | null,
  defaultDecimals = 2,
) {
  if (value == null) return '—'
  if (typeof value === 'string' && (decimals == null || isGiraText(value))) return value
  const number = typeof value === 'number' ? value : Number(value.trim().replace(',', '.'))
  return Number.isFinite(number)
    ? number.toLocaleString('de-DE', {
        minimumFractionDigits: decimals ?? 0,
        maximumFractionDigits: decimals ?? defaultDecimals,
      })
    : String(value)
}
