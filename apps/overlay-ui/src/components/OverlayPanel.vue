<script setup lang="ts">
import { computed } from 'vue'
import RecommendationItem from './RecommendationItem.vue'
import { words, statusText } from '../i18n/messages'
import type { Frame, Language } from '../overlay/types'
const props = defineProps<{ frame: Frame; language: Language }>()
const show = computed(() => props.frame.status === 'READY' && props.frame.recommendations.length > 0)
const text = computed(() => words[props.language])
</script>
<template>
  <section class="panel" aria-label="ManaMind">
    <div class="status" :class="{ 'status--ready': show }">
      <span class="status__dot" />{{ statusText(frame.status, language) }}
      <span v-if="frame.turn !== null" class="turn">{{ text.turn }} {{ frame.turn }}</span>
    </div>
    <ol v-if="show" class="recommendations">
      <RecommendationItem v-for="rec in frame.recommendations" :key="`${frame.revision}-${rec.rank}`" :rec="rec" :language="language" />
    </ol>
    <div v-else class="waiting"><span aria-hidden="true">◇</span><p>{{ frame.reason === 'CHECKPOINT_UNAVAILABLE' ? text.checkpoint : text.waiting }}</p></div>
    <p v-if="frame.policy_available === false && frame.reason !== 'CHECKPOINT_UNAVAILABLE'" class="policy-error">{{ text.checkpoint }}</p>
    <footer>
      <p>{{ text.footer }}</p><p class="positions">{{ text.order }}</p>
      <time v-if="show && frame.generated_at">{{ text.updated }} {{ new Date(frame.generated_at).toLocaleTimeString(language === 'ru' ? 'ru-RU' : 'en-US') }}</time>
      <details v-if="frame.reason"><summary>{{ text.details }}</summary>{{ frame.reason }}</details>
    </footer>
  </section>
</template>
<style scoped>
.panel { padding:12px; }
.status { display:flex; gap:8px; align-items:center; color:var(--c-text-dim); font-size:12px; padding:3px 2px 12px; }
.status__dot { width:7px; height:7px; border-radius:50%; background:#c6a5ff; }
.status--ready .status__dot { background:#74e0ba; }
.turn { margin-left:auto; color:var(--c-muted); }
.recommendations { display:flex; flex-direction:column; gap:8px; padding:0; margin:0; }
.waiting { text-align:center; padding:36px 12px; color:var(--c-text-dim); }
.waiting span { color:var(--c-accent); font-size:35px; }
.policy-error { color:#ffd58b; font-size:12px; }
footer { margin-top:16px; font-size:11px; color:var(--c-muted); }
footer p { margin:6px 0; } .positions { font-size:10px; } time { display:block; } details { margin-top:8px; }
</style>
