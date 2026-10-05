<script setup lang="ts">
import { computed } from 'vue'
import { LOCALES, locale, setLocale, t } from '../i18n'
import { formatLatency, statusLabel } from '../overlay/format'
import type { OverlayState } from '../overlay/types'

const props = defineProps<{ state: OverlayState }>()
const label = computed(() => statusLabel(props.state))
const latency = computed(() => formatLatency(props.state.latencyMs))
</script>

<template>
  <header class="head">
    <span class="head__brand">ManaMind</span>
    <span class="head__status" :class="`head__status--${state.status.toLowerCase()}`">
      <span class="head__dot" aria-hidden="true" />{{ label }}
    </span>
    <span class="head__meta">
      <span v-if="state.turn > 0">{{ t('turn') }} {{ state.turn }}</span>
      <span v-if="latency" :title="t('latency')">{{ latency }}</span>
    </span>
    <span class="head__lang" role="group" :aria-label="t('a11y.language')">
      <button
        v-for="l in LOCALES"
        :key="l"
        type="button"
        class="head__lang-btn"
        :aria-pressed="l === locale"
        :lang="l"
        @click="setLocale(l)"
      >
        {{ l.toUpperCase() }}
      </button>
    </span>
  </header>
</template>

<style scoped>
.head { display: flex; align-items: center; gap: 10px; padding: 10px 12px 8px; }
.head__brand { font-weight: 800; letter-spacing: 0.04em; font-size: 14px; }
.head__status { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--c-text-dim); white-space: nowrap; }
.head__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-muted); }
.head__status--ready .head__dot { background: var(--c-exact); }
.head__status--thinking .head__dot { background: var(--c-inferred); border-radius: 2px; }
.head__status--error .head__dot { background: var(--c-error); border-radius: 0; transform: rotate(45deg) scale(0.85); }
.head__meta { margin-left: auto; display: flex; gap: 8px; font-size: 12px; color: var(--c-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.head__lang { display: inline-flex; border: 1px solid var(--c-border); border-radius: 5px; overflow: hidden; flex: none; }
.head__lang-btn { background: transparent; color: var(--c-muted); border: 0; padding: 0 6px; font: inherit; font-size: 11px; font-weight: 700; line-height: 18px; cursor: pointer; }
.head__lang-btn + .head__lang-btn { border-left: 1px solid var(--c-border); }
.head__lang-btn[aria-pressed='true'] { background: var(--c-accent); color: #08131c; }
</style>
