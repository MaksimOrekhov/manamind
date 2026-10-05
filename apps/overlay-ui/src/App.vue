<script setup lang="ts">
import { computed, ref } from 'vue'
import OverlayPanel from './components/OverlayPanel.vue'
import { FIXTURES } from './overlay/fixtures'

// Dev-only fixture switcher: lives outside the overlay panel and is stripped from production builds.
const isDev = import.meta.env.DEV
const current = ref('mixed')
const state = computed(() => (FIXTURES.find((f) => f.key === current.value) ?? FIXTURES[0]).state)
</script>

<template>
  <main class="stage">
    <nav v-if="isDev" class="dev" aria-label="Mock fixtures (dev only)">
      <span class="dev__title">Mock state</span>
      <button
        v-for="f in FIXTURES"
        :key="f.key"
        type="button"
        class="dev__btn"
        :aria-pressed="f.key === current"
        @click="current = f.key"
      >
        {{ f.name }}
      </button>
    </nav>
    <OverlayPanel :state="state" />
  </main>
</template>

<style scoped>
.stage { display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 20px 12px; background: radial-gradient(circle at 30% 20%, #1c2536, #0b0e14 70%); min-height: 100vh; }
.dev { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; justify-content: center; max-width: 520px; }
.dev__title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--c-muted); }
.dev__btn { background: transparent; color: var(--c-text-dim); border: 1px solid var(--c-border); border-radius: 6px; padding: 3px 9px; font: inherit; font-size: 12px; cursor: pointer; }
.dev__btn[aria-pressed='true'] { background: var(--c-accent); color: #08131c; border-color: var(--c-accent); font-weight: 700; }
</style>
