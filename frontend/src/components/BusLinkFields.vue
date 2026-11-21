<script setup lang="ts">
const medium = defineModel<'tcp' | 'serial'>('medium')
const host = defineModel<string>('host')
const port = defineModel<number>('port')
const serialDevice = defineModel<string>('serialDevice')
const baudrate = defineModel<number>('baudrate')
</script>

<template>
  <label>
    Verbindung über
    <select class="settings-input" v-model="medium">
      <option value="tcp">IP / TCP</option>
      <option value="serial">USB / RS485</option>
    </select>
  </label>
  <template v-if="medium === 'serial'">
    <label>
      Serielles Gerät
      <input
        class="settings-input"
        v-model.trim="serialDevice"
        placeholder="/dev/ttyUSB0"
        autocomplete="off"
      />
    </label>
    <label>
      Baudrate
      <input
        class="settings-input"
        type="number"
        min="1200"
        max="115200"
        v-model.number="baudrate"
      />
    </label>
    <p class="section-hint">
      8 Datenbits, keine Parität, 1 Stoppbit. In Docker den Gerätepfad im Container angeben.
    </p>
  </template>
  <template v-else>
    <label>
      IP-Adresse
      <input class="settings-input" v-model.trim="host" autocomplete="off" />
    </label>
    <label>
      TCP-Port
      <input class="settings-input" type="number" min="1" max="65535" v-model.number="port" />
    </label>
  </template>
</template>
