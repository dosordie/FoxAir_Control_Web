import { ref } from 'vue'

type FavoriteStorage = Pick<Storage, 'getItem' | 'setItem'>
const KEY = 'foxair.favoriteRegisters'

function parseFavorites(value: string | null): number[] {
  try {
    const parsed: unknown = JSON.parse(value || '[]')
    if (!Array.isArray(parsed)) return []
    return [
      ...new Set(
        parsed.filter((id): id is number => Number.isInteger(id) && id > 0 && id <= 99999),
      ),
    ].slice(0, 1000)
  } catch {
    return []
  }
}

/** Store register IDs only, never measurement values, credentials or grants. */
export function useRegisterFavorites(storage?: FavoriteStorage) {
  let available = storage
  let initial: number[] = []
  try {
    available ??= window.localStorage
    initial = parseFavorites(available.getItem(KEY))
  } catch {
    /* Memory-only when storage is unavailable. */
  }
  const favoriteIds = ref(initial)
  const favoritesOnly = ref(false)
  const isFavorite = (id: number) => favoriteIds.value.includes(id)
  function toggleFavorite(id: number) {
    if (!Number.isInteger(id) || id <= 0 || id > 99999) return
    favoriteIds.value = isFavorite(id)
      ? favoriteIds.value.filter((item) => item !== id)
      : [...favoriteIds.value, id].slice(-1000)
    try {
      available?.setItem(KEY, JSON.stringify(favoriteIds.value))
    } catch {
      /* The current browser session remains usable. */
    }
  }
  return { favoriteIds, favoritesOnly, isFavorite, toggleFavorite }
}
