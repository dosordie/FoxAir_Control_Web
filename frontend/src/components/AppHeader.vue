<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { ArrowUpCircle, Settings2, ShieldCheck } from 'lucide-vue-next'
import type { Page } from '../types/navigation'
const props = defineProps<{
  version?: string
  updateAvailable?: boolean
  page: Page
  authenticated: boolean
  role?: string
  sessionUsername?: string
  ssoAvailable?: boolean
  busy: boolean
  secure: boolean
  error: string
}>()
const roleLabel = computed(() =>
  props.role === 'admin' ? 'Administrator' : props.role === 'operator' ? 'Bediener' : 'Leser',
)
const accountLabel = computed(() =>
  props.authenticated ? props.sessionUsername || roleLabel.value : 'Anmelden',
)
const username = defineModel<string>('username', { default: 'admin' })
const password = defineModel<string>('password', { required: true })
const loginOpen = defineModel<boolean>('loginOpen', { required: true })
const emit = defineEmits<{ navigate: [page: Page]; login: []; logout: []; ssoLogin: [] }>()
const menu = ref<HTMLElement | null>(null)
const usernameInput = ref<HTMLInputElement | null>(null)
const close = () => {
  loginOpen.value = false
  password.value = ''
}
function outside(event: PointerEvent) {
  if (loginOpen.value && !menu.value?.contains(event.target as Node)) close()
}
function escape(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}
watch(() => props.page, close)
watch(
  loginOpen,
  (open) => {
    if (open) usernameInput.value?.focus()
  },
  { flush: 'post' },
)
onMounted(() => {
  document.addEventListener('pointerdown', outside)
  document.addEventListener('keydown', escape)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', outside)
  document.removeEventListener('keydown', escape)
})
</script>
<template>
  <header class="shell-header">
    <button
      class="brand"
      type="button"
      @click="emit('navigate', 'home')"
      aria-label="Zur Übersicht"
    >
      <span class="brand-mark official-brand"><img src="/foxye-logo.png" alt="FoxAir-Logo" /></span>
      <span>
        <strong>FoxAir</strong>
        <span class="brand-caption">
          <small>CONTROL WEB</small>
          <span v-if="version" class="brand-version" :title="version">{{
            version.split('+')[0]
          }}</span>
        </span>
      </span>
    </button>
    <nav class="desktop-nav" aria-label="Hauptnavigation">
      <button :class="{ selected: page === 'home' }" @click="emit('navigate', 'home')">
        Übersicht
      </button>
      <button :class="{ selected: page === 'parameters' }" @click="emit('navigate', 'parameters')">
        Parameter
      </button>
      <button :class="{ selected: page === 'settings' }" @click="emit('navigate', 'settings')">
        Einstellungen
      </button>
    </nav>
    <div class="shell-header-right">
      <button
        v-if="updateAvailable"
        type="button"
        class="update-badge"
        title="Update verfügbar"
        aria-label="Update verfügbar – Einstellungen öffnen"
        @click="emit('navigate', 'settings')"
      >
        <ArrowUpCircle :size="17" />
        <span>Update</span>
      </button>
      <div class="user-menu" ref="menu">
        <button
          class="outlined-action"
          type="button"
          :aria-expanded="loginOpen"
          @click="loginOpen = !loginOpen"
        >
          <ShieldCheck :size="17" />
          <span class="account-name" :title="accountLabel">{{ accountLabel }}</span>
        </button>
        <div v-if="loginOpen" class="login-popover">
          <p>
            <strong>{{ authenticated ? accountLabel : 'Lesender Gast' }}</strong>
            <template v-if="authenticated && sessionUsername"> · {{ roleLabel }}</template>
          </p>
          <button v-if="authenticated" class="outlined-action" @click="emit('logout')">
            Abmelden
          </button>
          <form v-else @submit.prevent="emit('login')">
            <button
              v-if="ssoAvailable"
              type="button"
              class="outlined-action"
              :disabled="!secure || busy"
              @click="emit('ssoLogin')"
            >
              Mit Authelia anmelden
            </button>
            <label class="field-label"
              >Benutzername<input
                ref="usernameInput"
                class="settings-input"
                v-model="username"
                autocomplete="username"
            /></label>
            <label class="field-label" for="header-password">Passwort</label>
            <input
              id="header-password"
              class="settings-input"
              v-model="password"
              type="password"
              autocomplete="current-password"
              :disabled="!secure"
            />
            <p v-if="!secure" class="read-error">Anmeldung benötigt HTTPS.</p>
            <p v-if="error" class="read-error" role="alert">{{ error }}</p>
            <button class="main-action" :disabled="!secure || busy || !password">
              {{ busy ? 'Anmeldung läuft …' : 'Anmelden' }}
            </button>
          </form>
        </div>
      </div>
      <button
        class="header-icon"
        type="button"
        @click="emit('navigate', 'settings')"
        aria-label="App-Einstellungen"
      >
        <Settings2 :size="21" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.account-name {
  max-width: 13ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.login-popover strong {
  overflow-wrap: anywhere;
}
</style>
