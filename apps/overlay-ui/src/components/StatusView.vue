<script setup lang="ts">
import type { OverlayState } from '../overlay/types'

defineProps<{ state: OverlayState }>()
</script>

<template>
  <div class="status" :class="`status--${state.status.toLowerCase()}`" :role="state.status === 'ERROR' ? 'alert' : 'status'">
    <span v-if="state.status === 'THINKING'" class="status__pulse" aria-hidden="true" />
    <span v-else-if="state.status === 'ERROR'" class="status__icon" aria-hidden="true">!</span>
    <span v-else class="status__icon" aria-hidden="true">{{ state.activePlayer === 'OPPONENT' ? '…' : '○' }}</span>
    <p class="status__msg">{{ state.message }}</p>
  </div>
</template>

<style scoped>
.status { display: flex; align-items: center; gap: 12px; margin: 4px 12px 14px; padding: 14px; border-radius: 8px; background: var(--c-row); }
.status__msg { margin: 0; font-size: 14px; overflow-wrap: anywhere; }
.status__icon { flex: none; width: 26px; height: 26px; border-radius: 50%; border: 2px solid var(--c-muted); color: var(--c-muted); display: grid; place-items: center; font-weight: 800; }
.status--error { background: var(--c-error-bg); border: 1px solid var(--c-error); }
.status--error .status__icon { border-color: var(--c-error); color: var(--c-error); border-radius: 4px; }
.status__pulse { flex: none; width: 14px; height: 14px; border-radius: 3px; background: var(--c-inferred); animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.3; } }
@media (prefers-reduced-motion: reduce) { .status__pulse { animation: none; } }
</style>
