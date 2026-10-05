<script setup lang="ts">
import { computed } from 'vue'
import { SOURCE_INFO, countSources } from '../overlay/format'
import type { EvaluationSource, Recommendation } from '../overlay/types'

const props = defineProps<{ recommendations: Recommendation[] }>()
const counts = computed(() => countSources(props.recommendations))
const order: EvaluationSource[] = ['EXACT', 'INFERRED', 'NEURAL', 'UNAVAILABLE']
const visible = computed(() => order.filter((s) => counts.value[s] > 0))
const name = (s: EvaluationSource) => (s === 'UNAVAILABLE' ? 'N/A' : s.charAt(0) + s.slice(1).toLowerCase())
</script>

<template>
  <footer class="foot" aria-label="Evaluation source summary">
    <span v-for="s in visible" :key="s" class="foot__item" :title="SOURCE_INFO[s].summary">
      <span aria-hidden="true">{{ SOURCE_INFO[s].icon }}</span>
      {{ name(s) }} {{ counts[s] }}
    </span>
  </footer>
</template>

<style scoped>
.foot { display: flex; flex-wrap: wrap; gap: 4px 12px; padding: 8px 12px 10px; font-size: 12px; color: var(--c-text-dim); border-top: 1px solid var(--c-border); }
.foot__item { white-space: nowrap; }
</style>
