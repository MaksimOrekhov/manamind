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
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`
}

export interface SourceInfo {
  /** Player-facing label. */
  label: string
  /** Non-color shape cue. */
  icon: string
  /** One-line explanation, also used as tooltip. */
  summary: string
}

export const SOURCE_INFO: Record<EvaluationSource, SourceInfo> = {
  EXACT: { label: 'EXACT', icon: '●', summary: 'Exact simulation' },
  INFERRED: { label: 'INFERRED', icon: '◐', summary: 'Inferred simulation · evidence debt' },
  NEURAL: { label: 'NEURAL', icon: '◆', summary: 'Neural fallback · estimated, no exact result' },
  UNAVAILABLE: { label: 'N/A', icon: '✕', summary: 'Engine could not simulate action' },
}

export function statusLabel(state: OverlayState): string {
  if (state.status === 'IDLE') return 'Idle'
  if (state.status === 'THINKING') return 'Analyzing'
  if (state.status === 'ERROR') return 'Error'
  return state.activePlayer === 'OPPONENT' ? 'Waiting' : 'Ready'
}
