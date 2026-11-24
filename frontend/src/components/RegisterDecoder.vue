<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type CloudRow, type Register, type RegisterValue, type TransportId } from '../api'

const props = defineProps<{
  transport: TransportId
  valueFor: (register: number) => RegisterValue | null
  cloudRows?: CloudRow[]
}>()
const definitions = ref<Register[]>([])
const error = ref('')
const selectedTab = ref(0)
const tabButtons = ref<HTMLButtonElement[]>([])
const sections = [
  { title: 'Lastausgänge', registers: [2019, 2018] },
  { title: 'Schalterzustände', registers: [2034] },
]
function selectTab(index: number, focus = false) {
  selectedTab.value = index
  if (focus) tabButtons.value[index]?.focus()
}

onMounted(async () => {
  try {
    definitions.value = (
      await api.registers(
        '',
        '',
        sections.flatMap((section) => section.registers),
      )
    ).items
  } catch (cause) {
    error.value = (cause as Error).message
  }
})

const activeLowContacts = new Set([0, 1, 2, 3, 4, 5, 6, 9])
const cloudCodes: Partial<Record<number, string>> = { 2019: 'O01~023', 2034: 'S01~S10' }

function sample(register: number) {
  if (props.transport === 'cloud') {
    const code = cloudCodes[register]
    if (!code) return null
    const row = props.cloudRows?.find(
      (item) => item.code === code && item.register === register && item.confidence === 'confirmed',
    )
    const text = String(row?.value ?? '').trim()
    const raw = /^[01]{16}$/.test(text)
      ? Number.parseInt(text, 2)
      : /^\d{1,5}$/.test(text)
        ? Number(text)
        : NaN
    return row && Number.isInteger(raw) && raw <= 65535 ? { raw, quality: row.quality } : null
  }
  const row = props.valueFor(register)
  return row?.transport === props.transport && row.raw != null && Number.isInteger(row.raw)
    ? row
    : null
}

function decode(register: number) {
  const definition = definitions.value.find((row) => row.register === register)
  if (!definition) return []
  const raw = sample(register)?.raw
  if (register === 2018) {
    return [
      {
        bit: -1,
        label: 'Elektrischer Wassertankheizer',
        detail: definition.name,
        rawBit: raw === 0 || raw === 1 ? raw : null,
        on: raw === 0 ? false : raw === 1 ? true : null,
      },
    ]
  }
  return Object.entries(definition.bit_map ?? {}).flatMap(([key, label]) => {
    const bit = Number(key)
    if (!Number.isInteger(bit) || bit < 0 || bit > 15 || /reserviert|unbekannt/i.test(label))
      return []
    const set = raw == null ? null : Boolean(raw & (1 << bit))
    const activeLow = register === 2034 && activeLowContacts.has(bit)
    let name =
      register === 2019 && bit === 0
        ? 'Kompressor läuft'
        : register === 2019 && bit === 2
          ? 'Lüfter aktiv'
          : label.replace(/ \((?:0=AUS\/1=EIN|active-high:[^)]*)\)$/i, '')
    if (register === 2019) name = name.replace(/^0\d{2}\s+/, '')
    return [
      {
        bit,
        label: name,
        detail: label,
        rawBit: set === null ? null : Number(set),
        on: set === null ? null : activeLow ? !set : set,
      },
    ]
  })
}
</script>

<template>
  <div class="register-decoder">
    <p v-if="error" class="read-error" role="alert">{{ error }}</p>
    <p v-else-if="!definitions.length" role="status">Register werden geladen …</p>
    <p v-if="transport === 'cloud'" class="section-hint">
      Die Cloud liefert die Ausgänge 2019 und Eingangskontakte 2034. Für Register 2018 ist nur die
      Modbus-Zuordnung bestätigt.
    </p>
    <div class="decoder-tabs" role="tablist" aria-label="Statusgruppen">
      <button
        v-for="(section, index) in sections"
        :key="section.title"
        ref="tabButtons"
        type="button"
        class="outlined-action"
        role="tab"
        :id="'decoder-tab-' + index"
        :aria-selected="selectedTab === index"
        :aria-controls="'decoder-panel-' + index"
        :tabindex="selectedTab === index ? 0 : -1"
        @click="selectTab(index)"
        @keydown.right.prevent="selectTab((index + 1) % sections.length, true)"
        @keydown.left.prevent="selectTab((index + sections.length - 1) % sections.length, true)"
      >
        {{ section.title }}
      </button>
    </div>
    <div class="decoder-scroll" tabindex="0" aria-label="Registerwerte">
      <section
        v-for="(section, index) in sections"
        v-show="selectedTab === index"
        :key="section.title"
        role="tabpanel"
        :id="'decoder-panel-' + index"
        :aria-labelledby="'decoder-tab-' + index"
      >
        <div v-for="register in section.registers" :key="register">
          <p v-if="register === 2034" class="section-hint">
            Die bekannten Kontakte S01–S10 sind bei Rohbit 0 aktiv. Die beiden SG-Kontakte sind bei
            Rohbit 1 aktiv. Der Kontaktstatus allein zeigt keine Störung an.
          </p>
          <p class="section-hint">
            Register {{ register }} ·
            {{
              !sample(register)
                ? 'Wert fehlt'
                : sample(register)?.quality === 'stale'
                  ? 'Letzter bekannter Wert'
                  : 'Empfangener Wert'
            }}
          </p>
          <table
            v-if="decode(register).length"
            class="decoder-table"
            :aria-label="'Register ' + register"
          >
            <thead>
              <tr>
                <th scope="col">Bit</th>
                <th scope="col">Rohbit</th>
                <th scope="col">{{ section.title === 'Lastausgänge' ? 'Ausgang' : 'Kontakt' }}</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in decode(register)" :key="entry.bit">
                <td>{{ entry.bit < 0 ? '—' : entry.bit }}</td>
                <td>{{ entry.rawBit ?? '—' }}</td>
                <th scope="row" :title="entry.detail">{{ entry.label }}</th>
                <td :class="{ 'decoder-on': entry.on }">
                  {{ entry.on === null ? 'Unbekannt' : entry.on ? 'Ein' : 'Aus' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>
