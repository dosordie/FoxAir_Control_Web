<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Search, Star, X } from 'lucide-vue-next'

defineProps<{
  groups: { group: string; count: number }[]
  showGroups: boolean
  favoritesOnly: boolean
  favoriteCount: number
}>()
const search = defineModel<string>('search', { required: true })
const group = defineModel<string>('group', { required: true })
const emit = defineEmits<{ toggleFavorites: [] }>()
const expanded = ref(false)
const input = ref<HTMLInputElement | null>(null)
const toggle = ref<HTMLButtonElement | null>(null)
async function toggleSearch() {
  expanded.value = !expanded.value
  await nextTick()
  if (expanded.value) input.value?.focus()
}
function clearSearch() {
  search.value = ''
  input.value?.focus()
}
function closeSearch() {
  expanded.value = false
  toggle.value?.focus()
}
</script>

<template>
  <div class="parameter-filters" :class="{ 'search-expanded': expanded }">
    <div class="parameter-tools">
      <button
        ref="toggle"
        class="mobile-search-toggle filter-icon"
        :class="{ selected: expanded || search }"
        type="button"
        aria-label="Parametersuche öffnen oder schließen"
        :aria-expanded="expanded"
        aria-controls="parameter-search-field"
        @click="toggleSearch"
      >
        <Search :size="19" />
      </button>
      <label id="parameter-search-field" class="search-box parameter-search">
        <Search :size="19" />
        <input
          ref="input"
          v-model="search"
          type="search"
          placeholder="Code, Name oder Register suchen"
          aria-label="Parameter suchen"
          @keydown.esc="closeSearch"
        />
        <button
          v-if="search"
          type="button"
          class="clear-search"
          aria-label="Suche leeren"
          @click="clearSearch"
        >
          <X :size="17" />
        </button>
      </label>
      <button
        v-if="showGroups"
        type="button"
        class="outlined-action favorite-filter filter-icon"
        :class="{ selected: favoritesOnly }"
        :aria-pressed="favoritesOnly"
        :aria-label="
          favoritesOnly ? 'Alle Parameter anzeigen' : 'Nur Favoriten (' + favoriteCount + ')'
        "
        @click="emit('toggleFavorites')"
      >
        <Star :size="19" :fill="favoritesOnly ? 'currentColor' : 'none'" /><span
          class="favorite-filter-label"
          >{{ favoritesOnly ? 'Alle Parameter anzeigen' : 'Nur Favoriten' }} ({{
            favoriteCount
          }})</span
        >
      </button>
    </div>
    <div v-if="showGroups" class="parameter-groups" aria-label="Parametergruppen">
      <button
        v-for="entry in groups"
        :key="entry.group"
        type="button"
        class="group-chip"
        :class="{ active: group === entry.group }"
        @click="group = entry.group"
      >
        {{ entry.group }} <small>{{ entry.count }}</small>
      </button>
      <button
        type="button"
        class="group-chip"
        :class="{ active: group === '' }"
        @click="group = ''"
      >
        Alle
      </button>
    </div>
  </div>
</template>
