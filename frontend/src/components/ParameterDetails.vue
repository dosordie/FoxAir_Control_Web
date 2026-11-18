<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const media = window.matchMedia('(max-width: 600px)')
const mobile = ref(media.matches)
const container = ref<HTMLElement | null>(null)
function updateLayout() {
  if (container.value instanceof HTMLDialogElement && container.value.open) container.value.close()
  mobile.value = media.matches
}
async function open() {
  await nextTick()
  if (container.value instanceof HTMLDialogElement && !container.value.open)
    container.value.showModal()
}
function close() {
  if (container.value instanceof HTMLDialogElement) container.value.close()
}
onMounted(() => media.addEventListener('change', updateLayout))
onBeforeUnmount(() => media.removeEventListener('change', updateLayout))
defineExpose({ open })
</script>

<template>
  <component
    :is="mobile ? 'dialog' : 'section'"
    ref="container"
    class="panel register-detail"
    :class="{ 'parameter-detail-modal': mobile }"
    :aria-label="mobile ? 'Parameterdetails' : undefined"
    @click.self="mobile && close()"
  >
    <header v-if="mobile" class="parameter-detail-header">
      <strong>Parameterdetails</strong>
      <button
        type="button"
        class="outlined-action"
        aria-label="Parameterdetails schließen"
        autofocus
        @click="close"
      >
        Schließen
      </button>
    </header>
    <slot />
  </component>
</template>
