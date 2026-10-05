import { t, type MessageKey } from '../i18n'
import type { EvaluationSource, OverlayState, Recommendation } from './types'

/** 0.6739 -> "67%". Missing / non-finite scores render as an em dash. */
export function formatScore(score: number | undefined): string {
  if (score === undefined || !Number.isFinite(score)) return '—'
  const clamped = Math.min(1, Math.max(0, score))
  return `${Math.round(clamped * 100)}%`
}

export function sortByRank(recs: readonly Recommendation[]): Recommendation[] {
  return [...recs].sort((a, b) => a.rank - b.rank)
}

export type SourceCounts = Record<EvaluationSource, number>

export function countSources(recs: readonly Recommendation[]): SourceCounts {
  const counts: SourceCounts = { EXACT: 0, INFERRED: 0, NEURAL: 0, UNAVAILABLE: 0 }
  for (const r of recs) counts[r.source]++
  return counts
}

export function formatLatency(ms: number | undefined): string | undefined {
  if (ms === undefined) return undefined
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} ${t('unit.s')}` : `${Math.round(ms)} ${t('unit.ms')}`
}

/** Non-color shape cue per source; text comes from the i18n module. */
export const SOURCE_ICON: Record<EvaluationSource, string> = {
  EXACT: '●',
  INFERRED: '◐',
  NEURAL: '◆',
  UNAVAILABLE: '✕',
}

const SOURCE_KEYS: Record<EvaluationSource, { badge: MessageKey; summary: MessageKey; count: MessageKey }> = {
  EXACT: { badge: 'badge.exact', summary: 'summary.exact', count: 'count.exact' },
  INFERRED: { badge: 'badge.inferred', summary: 'summary.inferred', count: 'count.inferred' },
  NEURAL: { badge: 'badge.neural', summary: 'summary.neural', count: 'count.neural' },
  UNAVAILABLE: { badge: 'badge.unavailable', summary: 'summary.unavailable', count: 'count.unavailable' },
}

export const sourceBadge = (s: EvaluationSource): string => t(SOURCE_KEYS[s].badge)
export const sourceSummary = (s: EvaluationSource): string => t(SOURCE_KEYS[s].summary)
export const sourceCountLabel = (s: EvaluationSource): string => t(SOURCE_KEYS[s].count)

export function statusLabel(state: OverlayState): string {
  if (state.status === 'IDLE') return t('status.idle')
  if (state.status === 'THINKING') return t('status.thinking')
  if (state.status === 'ERROR') return t('status.error')
  return state.activePlayer === 'OPPONENT' ? t('status.waiting') : t('status.ready')
}

/**
 * Message for non-list states. Idle / analyzing / waiting texts are owned by the
 * overlay and localized here; an error message supplied by the runtime is shown as-is.
 */
export function statusMessage(state: OverlayState): string {
  if (state.status === 'ERROR') return state.message ?? t('msg.error')
  if (state.status === 'IDLE') return t('msg.idle')
  if (state.status === 'THINKING') return t('msg.thinking')
  return t('msg.waiting')
}
