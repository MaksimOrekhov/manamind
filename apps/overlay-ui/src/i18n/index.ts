import { ref } from 'vue'
import { messages, type MessageKey } from './messages'

export type { MessageKey }
export type Locale = 'ru' | 'en'

export const LOCALES: readonly Locale[] = ['ru', 'en']
export const DEFAULT_LOCALE: Locale = 'ru'
export const STORAGE_KEY = 'manamind.overlay.locale'

function readStored(): Locale {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'ru' || v === 'en') return v
  } catch {
    // storage unavailable: fall back to the default
  }
  return DEFAULT_LOCALE
}

function applyLang(l: Locale) {
  if (typeof document !== 'undefined') document.documentElement.lang = l
}

export const locale = ref<Locale>(readStored())
applyLang(locale.value)

/** Re-read the persisted choice (used by tests and on startup). */
export function initLocale(): void {
  locale.value = readStored()
  applyLang(locale.value)
}

export function setLocale(l: Locale): void {
  locale.value = l
  applyLang(l)
  try {
    localStorage.setItem(STORAGE_KEY, l)
  } catch {
    // not persisted; the choice still applies for this session
  }
}

/** Pure lookup, for non-reactive callers such as fixture builders. */
export function translate(l: Locale, key: MessageKey): string {
  return messages[l][key]
}

/** Reactive lookup: reads `locale`, so templates re-render on switch. */
export function t(key: MessageKey): string {
  return translate(locale.value, key)
}
