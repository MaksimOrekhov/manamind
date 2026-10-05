<script setup lang="ts">
import { computed, ref } from 'vue'
import { t } from '../i18n'
import { formatScore, sourceSummary } from '../overlay/format'
import type { Recommendation } from '../overlay/types'
import EvaluationBadge from './EvaluationBadge.vue'

const props = defineProps<{ rec: Recommendation }>()
const open = ref(false)
const detailsId = computed(() => `details-${props.rec.id}`)
const unavailable = computed(() => props.rec.source === 'UNAVAILABLE')
const notes = computed(() =>
  props.rec.evidence?.length ? props.rec.evidence : [sourceSummary(props.rec.source)],
)
</script>

<template>
  <li class="item" :class="{ 'item--top': rec.rank === 1 && !unavailable, 'item--na': unavailable }">
    <button
      type="button"
      class="item__row"
      :aria-expanded="open"
      :aria-controls="detailsId"
      @click="open = !open"
    >
      <span class="item__rank" data-testid="rank">{{ rec.rank }}</span>
      <span class="item__text">
        <span class="item__label">{{ rec.label }}</span>
        <span v-if="rec.detail" class="item__detail">{{ rec.detail }}</span>
        <EvaluationBadge :source="rec.source" />
      </span>
      <span class="item__score" data-testid="score" :aria-label="`${t('a11y.winProbability')} ${formatScore(rec.score)}`">
        {{ formatScore(rec.score) }}
      </span>
      <span class="item__chev" aria-hidden="true">{{ open ? '▾' : '▸' }}</span>
    </button>
    <ul v-if="open" :id="detailsId" class="item__notes" data-testid="details">
      <li v-for="n in notes" :key="n">{{ n }}</li>
      <li v-if="rec.fallbackEligible" class="item__muted">{{ t('note.fallbackEligible') }}</li>
    </ul>
  </li>
</template>

<style scoped>
.item {
  list-style: none;
  border-radius: 8px;
  background: var(--c-row);
  border: 1px solid transparent;
}
.item--top {
  background: var(--c-row-top);
  border-color: var(--c-accent);
  box-shadow: inset 3px 0 0 var(--c-accent);
}
.item__row {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto 12px;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 8px;
}
.item__rank {
  font-weight: 700;
  color: var(--c-muted);
  font-size: 13px;
  text-align: center;
}
.item--top .item__rank { color: var(--c-accent); font-size: 16px; }
.item__text { display: flex; flex-direction: column; align-items: flex-start; gap: 3px; min-width: 0; }
.item__label,
.item__detail {
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.item__label { font-size: 14px; font-weight: 600; }
.item--top .item__label { font-size: 16px; font-weight: 700; }
.item__detail { font-size: 12px; color: var(--c-muted); }
.item__score {
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.item--top .item__score { font-size: 24px; color: var(--c-accent); }
.item--na .item__label,
.item--na .item__score { color: var(--c-muted); }
.item__chev { color: var(--c-muted); font-size: 11px; }
.item__notes {
  margin: 0;
  padding: 0 12px 9px 40px;
  font-size: 12px;
  color: var(--c-text-dim);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.item__notes li { list-style: none; overflow-wrap: anywhere; }
.item__muted { color: var(--c-muted); }
</style>
