import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { api, type Register, type TransportId } from '../api'
import type { Page } from '../types/navigation'

/** Catalog navigation has no authority to start Modbus reads or write values. */
export function useRegisterCatalog(
  transport: Ref<TransportId>,
  page: Ref<Page>,
  invalidateSelection: () => void,
  favoriteIds: Readonly<Ref<number[] | undefined>> = ref(undefined),
) {
  const search = ref(''),
    selectedGroup = ref('')
  const registers = ref<Register[]>([])
  const catalogSize = ref(0),
    registerLoading = ref(false),
    catalogError = ref('')
  const registerGroups = ref<{ group: string; count: number }[]>([])
  const orderedGroups = computed(() =>
    registerGroups.value
      .filter((entry) => !['DIAG', 'ENG'].includes(entry.group.toUpperCase()))
      .sort(
        (a, b) =>
          Number(a.group.length !== 1) - Number(b.group.length !== 1) ||
          a.group.localeCompare(b.group, 'de'),
      ),
  )
  let requestNumber = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false

  async function loadRegisters() {
    const request = ++requestNumber
    const source = transport.value
    registerLoading.value = true
    catalogError.value = ''
    try {
      const result = await api.registers(search.value, selectedGroup.value, favoriteIds.value)
      if (disposed || request !== requestNumber || source !== transport.value) return
      registers.value = result.items.map((row) =>
        source === 'cloud' ? row : { ...row, cloud: null },
      )
      catalogSize.value = result.catalog_size
    } catch (error) {
      if (disposed || request !== requestNumber) return
      catalogError.value =
        error instanceof Error ? error.message : 'Registerkatalog nicht erreichbar'
      registers.value = []
    } finally {
      if (!disposed && request === requestNumber) registerLoading.value = false
    }
  }
  watch(transport, () => {
    requestNumber += 1
    registers.value = []
    registerLoading.value = false
  })
  watch(
    [page, transport],
    () => {
      requestNumber += 1
      registerLoading.value = false
      if (page.value === 'parameters') void loadRegisters()
    },
    { immediate: true },
  )
  watch([search, selectedGroup, favoriteIds] as const, (current, previous) => {
    requestNumber += 1
    if (current[1] !== previous[1]) invalidateSelection()
    clearTimeout(timer)
    timer = setTimeout(
      () => {
        if (page.value === 'parameters') void loadRegisters()
      },
      current[0] !== previous[0] ? 240 : 0,
    )
  })
  onMounted(async () => {
    try {
      const result = await api.registerGroups()
      if (!disposed) registerGroups.value = result.items
    } catch {
      if (!disposed) registerGroups.value = []
    }
  })
  onBeforeUnmount(() => {
    disposed = true
    requestNumber += 1
    clearTimeout(timer)
  })
  return {
    search,
    selectedGroup,
    registers,
    catalogSize,
    registerLoading,
    catalogError,
    orderedGroups,
    loadRegisters,
  }
}
