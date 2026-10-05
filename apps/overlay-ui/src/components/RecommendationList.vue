<script setup lang="ts">
import { computed } from 'vue'
import { sortByRank } from '../overlay/format'
import type { Recommendation } from '../overlay/types'
import RecommendationItem from './RecommendationItem.vue'

const props = defineProps<{ recommendations: Recommendation[] }>()
const ordered = computed(() => sortByRank(props.recommendations))
</script>

<template>
  <ol class="list" aria-label="Recommended actions">
    <RecommendationItem v-for="r in ordered" :key="r.id" :rec="r" />
  </ol>
</template>

<style scoped>
.list { margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
</style>
