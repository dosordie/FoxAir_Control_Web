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
const sections = [
  { title: 'Lastausgänge', registers: [2019, 2018] },
  { title: 'Schalterzustände', registers: [2034] },
]
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
    return [{ bit: -1, label: definition.name, on: raw === 0 ? false : raw === 1 ? true : null }]
  }
  return Object.entries(definition.bit_map ?? {}).flatMap(([key, label]) => {
    const bit = Number(key)
    if (!Number.isInteger(bit) || bit < 0 || bit > 15 || /reserviert|unbekannt/i.test(label))
      return []
    const set = raw == null ? null : Boolean(raw & (1 << bit))
    const activeLow = register === 2034 && bit < 10
    const name = label.replace(/ \((?:0=AUS\/1=EIN|active-high:[^)]*)\)$/i, '')
    return [{ bit, label: name, on: set === null ? null : activeLow ? !set : set }]
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
    <section v-for="section in sections" :key="section.title">
      <h3>{{ section.title }}</h3>
      <div v-for="register in section.registers" :key="register">
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
        <dl>
          <div v-for="entry in decode(register)" :key="entry.bit">
            <dt>{{ entry.label }}</dt>
            <dd :class="{ 'decoder-on': entry.on }">
              {{ entry.on === null ? 'Unbekannt' : entry.on ? 'Ein' : 'Aus' }}
            </dd>
          </div>
        </dl>
      </div>
    </section>
  </div>
</template>
