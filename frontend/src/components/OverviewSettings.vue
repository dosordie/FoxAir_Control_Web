<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { GripVertical } from 'lucide-vue-next'
import { api, type GiraOption } from '../api'
import {
  defaultOverview,
  glanceActions,
  overviewFields,
  type OverviewLayout,
  type OverviewProfile,
} from '../overview'

const props = defineProps<{ layout: OverviewLayout; giraRevision: number }>()
const emit = defineEmits<{ saved: [OverviewLayout] }>()
const profile = ref<OverviewProfile>('desktop')
const area = ref<'hero' | 'glance'>('hero')
const layoutKey = computed(() =>
  area.value === 'hero'
    ? profile.value
    : profile.value === 'mobile'
      ? 'mobile_glance'
      : 'desktop_glance',
)

const selectedCount = computed(
  () => draft.value[layoutKey.value].filter((key) => !key.startsWith('spacer:')).length,
)
const spareSlots = Array.from({ length: 6 }, (_, index) => 'spacer:' + (index + 1))
const nextSpacer = computed(() =>
  spareSlots.find((key) => !draft.value[layoutKey.value].includes(key)),
)

const columnsKey = computed(() =>
  profile.value === 'mobile' ? 'mobile_columns' : 'desktop_columns',
)
const draft = ref<OverviewLayout>(structuredClone(defaultOverview))
const busy = ref(false)
const dragged = ref<string | null>(null)
const dropIndex = ref<number | null>(null)
const orderList = ref<HTMLOListElement>()
let touchPointer: number | null = null
let scrollFrame = 0

function clearDrag() {
  dragged.value = null
  dropIndex.value = null
  touchPointer = null
  cancelAnimationFrame(scrollFrame)
  scrollFrame = 0
}
watch([layoutKey, busy], clearDrag)
onBeforeUnmount(clearDrag)
const gira = ref<GiraOption[]>([])
const giraError = ref('')
watch(
  () => props.giraRevision,
  async (_, __, onCleanup) => {
    let active = true
    onCleanup(() => {
      active = false
    })
    try {
      const result = await api.giraOverviewOptions()
      if (active) {
        gira.value = result.items ?? []
        giraError.value = ''
      }
    } catch (cause) {
      if (active) giraError.value = (cause as Error).message
    }
  },
  { immediate: true },
)
const message = ref('')
const error = ref('')
watch(
  () => props.layout,
  (value) => {
    draft.value = {
      ...defaultOverview,
      ...value,
      mobile: [...value.mobile],
      desktop: [...value.desktop],
      mobile_glance: [...(value.mobile_glance ?? defaultOverview.mobile_glance)],
      desktop_glance: [...(value.desktop_glance ?? defaultOverview.desktop_glance)],
    }
  },
  { immediate: true },
)

function labelFor(key: string) {
  if (key.startsWith('spacer:')) return 'Leerplatz ' + key.slice(7)
  return (
    overviewFields[key as keyof typeof overviewFields]?.label ||
    glanceActions[key as keyof typeof glanceActions] ||
    gira.value.find((item) => item.layout_key === key)?.name ||
    gira.value.find((item) => item.layout_key === key)?.object_key ||
    'Gira-Objekt'
  )
}

function move(key: string, index: number) {
  const keys = draft.value[layoutKey.value]
  const from = keys.indexOf(key)
  if (from < 0 || index < 0 || index >= keys.length || from === index) return
  keys.splice(from, 1)
  keys.splice(index, 0, key)
}

function startDrag(key: string, event: DragEvent) {
  dragged.value = key
  event.dataTransfer?.setData('text/plain', key)
}

function drop(target: number) {
  if (dragged.value) move(dragged.value, target)
  clearDrag()
}

function startTouchDrag(key: string, event: PointerEvent) {
  if (event.pointerType === 'mouse' || !event.isPrimary || busy.value) return
  touchPointer = event.pointerId
  dragged.value = key
  const handle = event.currentTarget as HTMLElement
  handle.setPointerCapture(event.pointerId)
}

function targetAt(x: number, y: number) {
  const row = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-order-index]')
  dropIndex.value =
    row && row.parentElement === orderList.value ? Number(row.dataset.orderIndex) : null
}

function trackTouchDrag(event: PointerEvent) {
  if (event.pointerId !== touchPointer) return
  const { clientX, clientY } = event
  targetAt(clientX, clientY)
  cancelAnimationFrame(scrollFrame)
  const distance = clientY < 72 ? -10 : clientY > window.innerHeight - 72 ? 10 : 0
  if (!distance) return
  function scroll() {
    const previous = window.scrollY
    window.scrollBy(0, distance)
    targetAt(clientX, clientY)
    if (window.scrollY !== previous) scrollFrame = requestAnimationFrame(scroll)
  }
  scrollFrame = requestAnimationFrame(scroll)
}

function endTouchDrag(event: PointerEvent) {
  if (event.pointerId !== touchPointer) return
  targetAt(event.clientX, event.clientY)
  if (dropIndex.value !== null) drop(dropIndex.value)
  else clearDrag()
}

function addSpacer() {
  if (nextSpacer.value) draft.value[layoutKey.value].push(nextSpacer.value)
}

function restoreDefault() {
  draft.value[layoutKey.value] = [...defaultOverview[layoutKey.value]]
  if (area.value === 'hero') draft.value[columnsKey.value] = defaultOverview[columnsKey.value]
}

function toggle(key: string, checked: boolean) {
  const keys = draft.value[layoutKey.value]
  if (checked && !keys.includes(key)) keys.push(key)
  if (!checked) {
    draft.value[layoutKey.value] = keys.filter((item) => item !== key)
  }
}

async function save() {
  busy.value = true
  message.value = ''
  error.value = ''
  try {
    emit('saved', await api.saveOverview(draft.value))
    message.value = 'Übersicht gespeichert.'
  } catch (cause) {
    error.value = (cause as Error).message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="settings-panel panel">
    <h2>Übersicht</h2>
    <label class="field-label" for="overview-profile">Anzeigeprofil</label>
    <select id="overview-profile" v-model="profile" class="settings-input">
      <option value="desktop">Tablet und PC</option>
      <option value="mobile">Smartphone</option>
    </select>
    <label class="field-label" for="overview-area">Bereich</label>
    <select id="overview-area" v-model="area" class="settings-input">
      <option value="hero">Oberer Bereich</option>
      <option value="glance">Auf einen Blick</option>
    </select>
    <label v-if="area === 'hero'" class="field-label" for="overview-columns">Werte pro Zeile</label>
    <select
      v-if="area === 'hero'"
      id="overview-columns"
      v-model.number="draft[columnsKey]"
      class="settings-input"
    >
      <option v-for="count in profile === 'mobile' ? 4 : 9" :key="count" :value="count">
        {{ count }}
      </option>
    </select>
    <p class="section-hint">{{ selectedCount }} Werte ausgewählt (einschließlich Gira).</p>
    <p v-if="giraError" class="read-error" role="alert">Gira-Liste: {{ giraError }}</p>
    <fieldset :disabled="busy" class="overview-options">
      <legend>
        {{ area === 'hero' ? 'Werte im oberen Bereich' : 'Anzeigen und Bedienknöpfe' }}
      </legend>
      <label v-for="(field, key) in overviewFields" :key="key" class="settings-check">
        <input
          type="checkbox"
          :checked="draft[layoutKey].includes(key)"
          @change="toggle(key, ($event.target as HTMLInputElement).checked)"
        />
        {{ field.label }}
      </label>
      <template v-if="area === 'glance'">
        <label v-for="(label, key) in glanceActions" :key="key" class="settings-check">
          <input
            type="checkbox"
            :checked="draft[layoutKey].includes(key)"
            @change="toggle(key, ($event.target as HTMLInputElement).checked)"
          />
          {{ label }}
        </label>
      </template>
      <label v-for="item in gira" :key="item.layout_key" class="settings-check">
        <input
          type="checkbox"
          :checked="draft[layoutKey].includes(item.layout_key)"
          @change="toggle(item.layout_key, ($event.target as HTMLInputElement).checked)"
        />
        {{ item.name || item.object_key }}
      </label>
      <label
        v-for="key in draft[layoutKey].filter(
          (key) => key.startsWith('gira:') && !gira.some((item) => item.layout_key === key),
        )"
        :key="key"
        class="settings-check"
      >
        <input type="checkbox" checked @change="toggle(key, false)" /> Gira-Objekt derzeit nicht
        verfügbar
      </label>
    </fieldset>
    <fieldset
      v-if="draft[layoutKey].length || area === 'glance'"
      :disabled="busy"
      class="overview-order"
    >
      <legend>Reihenfolge</legend>
      <button
        v-if="area === 'glance'"
        type="button"
        class="outlined-action"
        :disabled="!nextSpacer"
        @click="addSpacer"
      >
        Leerplatz hinzufügen
      </button>
      <p class="section-hint">Am Griff ziehen oder mit den Pfeilen verschieben.</p>
      <ol ref="orderList" @dragleave.self="dropIndex = null">
        <li
          v-for="(key, index) in draft[layoutKey]"
          :key="key"
          :data-order-index="index"
          :class="{ 'overview-drop-target': dropIndex === index && dragged !== key }"
          :draggable="!busy"
          @dragstart="startDrag(key, $event)"
          @dragend="clearDrag"
          @dragover.prevent="dropIndex = dragged ? index : null"
          @drop.prevent="drop(index)"
        >
          <span
            class="overview-drag-handle"
            title="Zum Sortieren ziehen"
            aria-hidden="true"
            @pointerdown="startTouchDrag(key, $event)"
            @pointermove="trackTouchDrag"
            @pointerup="endTouchDrag"
            @pointercancel="clearDrag"
            @lostpointercapture="clearDrag"
          >
            <GripVertical :size="18" />
          </span>
          <span class="overview-order-label">{{ labelFor(key) }}</span>
          <button
            v-if="key.startsWith('spacer:')"
            type="button"
            class="outlined-action"
            :aria-label="labelFor(key) + ' entfernen'"
            @click="toggle(key, false)"
          >
            Entfernen
          </button>
          <button
            type="button"
            class="outlined-action"
            :aria-label="labelFor(key) + ' nach oben'"
            :disabled="index === 0"
            @click="move(key, index - 1)"
          >
            ↑
          </button>
          <button
            type="button"
            class="outlined-action"
            :aria-label="labelFor(key) + ' nach unten'"
            :disabled="index === draft[layoutKey].length - 1"
            @click="move(key, index + 1)"
          >
            ↓
          </button>
        </li>
      </ol>
    </fieldset>
    <button type="button" class="outlined-action" :disabled="busy" @click="restoreDefault">
      Standard wiederherstellen
    </button>
    <button type="button" class="outlined-action" :disabled="busy" @click="save">
      Übersicht speichern
    </button>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="error" class="read-error" role="alert">{{ error }}</p>
  </section>
</template>
