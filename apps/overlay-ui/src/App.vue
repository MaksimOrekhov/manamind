<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import OverlayPanel from './components/OverlayPanel.vue'
import { words, statusText } from './i18n/messages'
import { acceptFrame, disconnected, emptyFrame } from './overlay/feed'
import type { Preferences } from './overlay/types'
const frame = ref(emptyFrame())
const settings = ref<Preferences>({ language: 'ru', collapsed: false, opacity: .92 })
let timer: ReturnType<typeof setTimeout> | undefined
let watchdog: ReturnType<typeof setInterval> | undefined
let stopped = false, lastResponse = 0, loaded = false
let generation = 0
let requestStarted = 0, pending = false
async function poll() {
  const attempt = ++generation
  requestStarted = Date.now(); pending = true
  try {
    const api = window.pywebview?.api
    if (!api) throw new Error('Disconnected')
    const next = await api.get_frame()
    if (stopped || attempt !== generation) return
    lastResponse = Date.now()
    frame.value = acceptFrame(frame.value, next)
    if (!loaded && next.preferences) { settings.value = next.preferences; loaded = true }
  } catch { if (attempt === generation) frame.value = disconnected(frame.value) }
  if (attempt !== generation || stopped) return
  pending = false
  if (!stopped) timer = setTimeout(poll, 100)
}
watch(settings, async () => {
  document.documentElement.lang = settings.value.language
  if (loaded) {
    try { await window.pywebview?.api.set_preferences({ ...settings.value }) } catch { frame.value = disconnected(frame.value) }
  }
}, { deep: true })
onMounted(() => {
  poll()
  watchdog = setInterval(() => {
    if (Date.now() - lastResponse > 2000) frame.value = disconnected(frame.value)
    if (pending && Date.now() - requestStarted > 2000) {
      // A timed-out promise may still resolve. Supersede it before reconnecting.
      generation++; poll()
    }
  }, 250)
})
onUnmounted(() => { stopped = true; generation++; clearTimeout(timer); clearInterval(watchdog) })
function close() { window.pywebview?.api.close() }
</script>
<template>
  <main>
    <header>
      <div class="brand pywebview-drag-region">ManaMind <small>{{ settings.collapsed ? statusText(frame.status, settings.language) : 'Policy v2' }}</small></div>
      <button class="language" @click="settings.language = settings.language === 'ru' ? 'en' : 'ru'">{{ settings.language.toUpperCase() }}</button>
      <button :aria-label="settings.collapsed ? words[settings.language].restore : words[settings.language].collapse" @click="settings.collapsed = !settings.collapsed">{{ settings.collapsed ? '＋' : '−' }}</button>
      <button :aria-label="words[settings.language].close" @click="close">×</button>
    </header>
    <div v-if="!settings.collapsed" class="body">
      <OverlayPanel :frame="frame" :language="settings.language" />
      <label class="opacity">{{ words[settings.language].opacity }}<input v-model.number="settings.opacity" type="range" min="0.55" max="1" step="0.01" /></label>
    </div>
  </main>
</template>
<style scoped>
main { min-height:100vh; background:#12161f; }
header { display:flex; align-items:center; gap:5px; height:56px; padding:0 12px; border-bottom:1px solid var(--c-border); }
.brand { display:flex; flex:1; align-items:baseline; gap:8px; font-weight:750; font-size:17px; cursor:move; min-width:0; }
small { color:var(--c-muted); font-size:10px; font-weight:400; overflow:hidden; white-space:nowrap; }
button { background:transparent; color:var(--c-text-dim); border:1px solid transparent; border-radius:6px; width:28px; height:28px; cursor:pointer; font-size:20px; }
button:hover { border-color:var(--c-border); background:var(--c-row); } .language { font-size:11px; }
.body { height:calc(100vh - 56px); overflow:auto; }
.opacity { display:flex; align-items:center; gap:12px; color:var(--c-muted); font-size:10px; padding:0 14px 14px; }
input { width:100%; accent-color:var(--c-accent); }
</style>
