import type { OverlayState, Recommendation } from './types'

const EXACT_NOTE = 'Exact simulation'
const INFERRED_NOTES = ['Inferred simulation · evidence debt', 'Rules not fully verified']
const NEURAL_NOTES = ['Neural fallback', 'No exact child state']

const exactOnly: Recommendation[] = [
  { id: 'e1', rank: 1, label: 'Fireball → Enemy Hero', score: 0.67, source: 'EXACT', evidence: [EXACT_NOTE] },
  { id: 'e2', rank: 2, label: 'Play Sir Finley Mrrgglton', detail: 'Hero Power: swap to Lightning Jolt', score: 0.58, source: 'EXACT', evidence: [EXACT_NOTE] },
  { id: 'e3', rank: 3, label: 'End Turn', score: 0.29, source: 'EXACT', evidence: [EXACT_NOTE] },
]

const mixed: Recommendation[] = [
  { id: 'm1', rank: 1, label: 'Fireball → Enemy Hero', score: 0.67, source: 'EXACT', evidence: [EXACT_NOTE] },
  { id: 'm2', rank: 2, label: 'Play Unknown Card', detail: 'New card, no simulation rules yet', score: 0.61, source: 'NEURAL', evidence: NEURAL_NOTES, fallbackEligible: true },
  { id: 'm3', rank: 3, label: 'Attack with Murloc Tidehunter → Enemy Hero', score: 0.54, source: 'INFERRED', evidence: INFERRED_NOTES },
  { id: 'm4', rank: 4, label: 'End Turn', score: 0.29, source: 'EXACT', evidence: [EXACT_NOTE] },
]

const partial: Recommendation[] = [
  { id: 'p1', rank: 1, label: 'Play Unknown Card', score: 0.63, source: 'NEURAL', evidence: NEURAL_NOTES, fallbackEligible: true },
  { id: 'p2', rank: 2, label: 'Hero Power', score: 0.55, source: 'EXACT', evidence: [EXACT_NOTE] },
  { id: 'p3', rank: 3, label: 'Play Card With Dynamic Discover Pool', source: 'UNAVAILABLE', evidence: ['Engine could not simulate action'] },
  { id: 'p4', rank: 4, label: 'End Turn', score: 0.31, source: 'EXACT', evidence: [EXACT_NOTE] },
]

const stress: Recommendation[] = [
  {
    id: 's1',
    rank: 1,
    label: 'Play The Ancient One of Unreasonably Long Names → Friendly Hyperextended Minion',
    detail: 'A very long detail line describing a choose-one effect with several nested targeting conditions that must not overflow',
    score: 0.7391,
    source: 'INFERRED',
    evidence: [...INFERRED_NOTES, 'Dependency token unresolved', 'Pool snapshot approximate'],
  },
  { id: 's2', rank: 2, label: 'Trade Supercalifragilisticexpialidocious_Minion_Name', score: 0.6, source: 'EXACT' },
  { id: 's3', rank: 3, label: 'Play Unknown Card', source: 'NEURAL', evidence: NEURAL_NOTES },
  { id: 's4', rank: 4, label: 'Use Location', source: 'UNAVAILABLE' },
  { id: 's5', rank: 5, label: 'End Turn', score: 0.12, source: 'EXACT' },
]

export interface FixtureEntry {
  key: string
  name: string
  state: OverlayState
}

const base = { gameId: 'mock-1', activePlayer: 'SELF' as const }

export const FIXTURES: FixtureEntry[] = [
  { key: 'idle', name: 'Idle', state: { turn: 0, activePlayer: 'SELF', status: 'IDLE', message: 'No active Hearthstone match', recommendations: [] } },
  { key: 'thinking', name: 'Thinking', state: { ...base, turn: 7, status: 'THINKING', message: 'Analyzing position…', recommendations: [] } },
  { key: 'exact', name: 'Exact', state: { ...base, turn: 7, status: 'READY', latencyMs: 182, recommendations: exactOnly } },
  { key: 'mixed', name: 'Mixed', state: { ...base, turn: 7, status: 'READY', latencyMs: 640, recommendations: mixed } },
  { key: 'partial', name: 'Partial', state: { ...base, turn: 7, status: 'READY', latencyMs: 910, recommendations: partial } },
  { key: 'error', name: 'Error', state: { ...base, turn: 7, status: 'ERROR', message: 'The engine rejected this position. No recommendation is shown.', recommendations: [] } },
  { key: 'opponent', name: 'Opponent', state: { ...base, turn: 6, activePlayer: 'OPPONENT', status: 'READY', message: 'Waiting for opponent…', recommendations: [] } },
  { key: 'stress', name: 'Stress', state: { ...base, turn: 10, status: 'READY', latencyMs: 1480, recommendations: stress } },
]
