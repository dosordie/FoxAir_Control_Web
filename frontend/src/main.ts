import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')


if (import.meta.env.PROD && window.isSecureContext && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js', {updateViaCache:'none'}).catch(() => {
      // A failed offline-shell installation must not prevent normal online use.
    })
  })
}
