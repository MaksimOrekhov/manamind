<script setup lang="ts">
import { computed } from 'vue'
import { words } from '../i18n/messages'
import type { Language, Recommendation } from '../overlay/types'
const props = defineProps<{ rec: Recommendation; language: Language }>()
const view = computed(() => props.rec.view[props.language])
const riskWarning = computed(() => props.rec.risk_warning?.[props.language] ?? '')
</script>
<template>
  <li class="item" :class="{ 'item--top': rec.rank === 1 }">
    <div class="item__heading"><span class="item__rank">{{ rec.rank }}</span><strong>{{ view.verb }}</strong></div>
    <div v-if="view.source" class="item__source">{{ view.source }}</div>
    <div v-if="view.target" class="item__target"><span aria-hidden="true">↓</span>{{ view.target }}</div>
    <div v-if="view.placement" class="item__placement">{{ view.placement }}</div>
    <p v-if="rec.rank === 1 && riskWarning" class="item__risk-warning">{{ riskWarning }}</p>
    <p v-if="view.warning" class="item__warning">{{ view.warning }}</p>
    <details>
      <summary>{{ words[language].details }}</summary>
      <p>{{ words[language].logit }}: {{ rec.logit.toFixed(3) }}</p>
      <pre>{{ JSON.stringify(rec.action, null, 2) }}</pre>
    </details>
  </li>
</template>
<style scoped>
.item { list-style:none; padding:12px; background:var(--c-row); border:1px solid var(--c-border); border-radius:10px; }
.item--top { background:var(--c-row-top); border-color:var(--c-accent); box-shadow:inset 3px 0 var(--c-accent); padding:16px; }
.item__heading { display:flex; align-items:center; gap:10px; font-size:12px; letter-spacing:.05em; color:var(--c-accent); }
.item--top .item__heading { font-size:16px; }
.item__rank { border:1px solid currentColor; border-radius:50%; width:22px; height:22px; text-align:center; }
.item__source,.item__target,.item__placement { margin-top:7px; overflow-wrap:anywhere; line-height:1.45; }
.item--top .item__source,.item--top .item__target { font-size:16px; font-weight:600; }
.item__target span { display:block; color:var(--c-accent); font-size:18px; line-height:1; margin:7px 0; }
.item__placement { color:var(--c-text-dim); }
.item__warning,.item__risk-warning { color:#ffd58b; font-size:12px; }
.item__risk-warning { font-weight:700; padding:8px; border:1px solid #80653d; border-radius:7px; background:#32291d; }
details { font-size:11px; color:var(--c-muted); margin-top:8px; }
summary { cursor:pointer; }
pre { white-space:pre-wrap; overflow-wrap:anywhere; }
</style>
