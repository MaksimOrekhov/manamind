<script setup lang="ts">
import { computed } from 'vue'
import { t } from '../i18n'
import type { OverlayState } from '../overlay/types'
import OverlayFooter from './OverlayFooter.vue'
import OverlayHeader from './OverlayHeader.vue'
import RecommendationList from './RecommendationList.vue'
import StatusView from './StatusView.vue'

const props = defineProps<{ state: OverlayState }>()
const showList = computed(
  () => props.state.status === 'READY' && props.state.activePlayer === 'SELF' && props.state.recommendations.length > 0,
)
</script>

<template>
  <section class="panel" :aria-label="t('a11y.panel')">
    <OverlayHeader :state="state" />
    <div v-if="showList" class="panel__body">
      <RecommendationList :recommendations="state.recommendations" />
    </div>
    <StatusView v-else :state="state" />
    <OverlayFooter v-if="showList" :recommendations="state.recommendations" />
  </section>
</template>

<style scoped>
.panel {
  width: 100%;
  max-width: 400px;
  max-height: 550px;
  overflow-y: auto;
  background: var(--c-panel);
  border: 1px solid var(--c-border);
  border-radius: 12px;
  backdrop-filter: blur(8px);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.5);
}
.panel__body { padding: 0 8px 8px; }
</style>
