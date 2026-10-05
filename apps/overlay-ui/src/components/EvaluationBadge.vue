<script setup lang="ts">
import { SOURCE_ICON, sourceBadge, sourceSummary } from '../overlay/format'
import type { EvaluationSource } from '../overlay/types'

defineProps<{ source: EvaluationSource }>()
</script>

<template>
  <span
    class="badge"
    :class="`badge--${source.toLowerCase()}`"
    :title="sourceSummary(source)"
    :aria-label="sourceSummary(source)"
    data-testid="source-badge"
  >
    <span class="badge__icon" aria-hidden="true">{{ SOURCE_ICON[source] }}</span>
    <span class="badge__label">{{ sourceBadge(source) }}</span>
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
