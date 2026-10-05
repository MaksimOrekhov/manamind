<script setup lang="ts">
import { computed } from 'vue'
import { SOURCE_INFO } from '../overlay/format'
import type { EvaluationSource } from '../overlay/types'

const props = defineProps<{ source: EvaluationSource }>()
const info = computed(() => SOURCE_INFO[props.source])
</script>

<template>
  <span
    class="badge"
    :class="`badge--${source.toLowerCase()}`"
    :title="info.summary"
    :aria-label="info.summary"
    data-testid="source-badge"
  >
    <span class="badge__icon" aria-hidden="true">{{ info.icon }}</span>
    <span class="badge__label">{{ info.label }}</span>
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px 1px 6px;
  border: 1px solid currentColor;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: 16px;
  white-space: nowrap;
}
.badge__icon { font-size: 9px; }
.badge--exact { color: var(--c-exact); }
.badge--inferred { color: var(--c-inferred); border-style: dashed; }
.badge--neural { color: var(--c-neural); border-radius: 9px; }
.badge--unavailable { color: var(--c-muted); border-style: dotted; }
</style>
