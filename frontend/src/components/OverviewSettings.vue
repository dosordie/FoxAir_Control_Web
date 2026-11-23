<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api, type GiraOption } from '../api'
import {
  defaultOverview,
  overviewFields,
  type OverviewLayout,
  type OverviewProfile,
} from '../overview'

const props = defineProps<{ layout: OverviewLayout; giraRevision: number }>()
const emit = defineEmits<{ saved: [OverviewLayout] }>()
const profile = ref<OverviewProfile>('desktop')
const columnsKey = computed(() =>
  profile.value === 'mobile' ? 'mobile_columns' : 'desktop_columns',
)
const draft = ref<OverviewLayout>(structuredClone(defaultOverview))
const busy = ref(false)
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
    }
  },
  { immediate: true },
)

function restoreDefault() {
  draft.value[profile.value] = [...defaultOverview[profile.value]]
  draft.value[columnsKey.value] = defaultOverview[columnsKey.value]
}

function toggle(key: string, checked: boolean) {
  const keys = draft.value[profile.value]
  if (checked && keys.length < 12) keys.push(key)
  if (!checked) {
    draft.value[profile.value] = keys.filter((item) => item !== key)
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
    <label class="field-label" for="overview-columns">Werte pro Zeile</label>
    <select id="overview-columns" v-model.number="draft[columnsKey]" class="settings-input">
      <option v-for="count in profile === 'mobile' ? 4 : 9" :key="count" :value="count">
        {{ count }}
      </option>
    </select>
    <p class="section-hint">
      {{ draft[profile].length }} von 12 Werten ausgewählt (einschließlich Gira).
    </p>
    <p v-if="giraError" class="read-error" role="alert">Gira-Liste: {{ giraError }}</p>
    <fieldset :disabled="busy" class="overview-options">
      <legend>Werte im oberen Bereich</legend>
      <label v-for="(field, key) in overviewFields" :key="key" class="settings-check">
        <input
          type="checkbox"
          :checked="draft[profile].includes(key)"
          :disabled="draft[profile].length >= 12 && !draft[profile].includes(key)"
          @change="toggle(key, ($event.target as HTMLInputElement).checked)"
        />
        {{ field.label }}
      </label>
      <label v-for="item in gira" :key="item.layout_key" class="settings-check">
        <input
          type="checkbox"
          :checked="draft[profile].includes(item.layout_key)"
          :disabled="draft[profile].length >= 12 && !draft[profile].includes(item.layout_key)"
          @change="toggle(item.layout_key, ($event.target as HTMLInputElement).checked)"
        />
        {{ item.name || item.object_key }}
      </label>
      <label
        v-for="key in draft[profile].filter(
          (key) => key.startsWith('gira:') && !gira.some((item) => item.layout_key === key),
        )"
        :key="key"
        class="settings-check"
      >
        <input type="checkbox" checked @change="toggle(key, false)" /> Gira-Objekt derzeit nicht
        verfügbar
      </label>
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
