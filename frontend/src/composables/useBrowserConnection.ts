import { onBeforeUnmount, onMounted, ref } from 'vue'

export function useBrowserConnection() {
  const browserOnline = ref(navigator.onLine)
  const update = () => {
    browserOnline.value = navigator.onLine
  }
  onMounted(() => {
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('online', update)
    window.removeEventListener('offline', update)
  })
  return { browserOnline }
}
