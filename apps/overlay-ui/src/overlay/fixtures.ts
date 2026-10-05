import { translate, type Locale } from '../i18n'
import type { OverlayState, Recommendation } from './types'

/**
 * Mock action labels. Real recommendation DTOs are expected to arrive with
 * display-ready, already localized labels; this table only exists for the mocks.
 */
const TEXT = {
  fireball: { ru: 'Огненный шар → герой противника', en: 'Fireball → Enemy Hero' },
  finley: { ru: 'Сыграть Сэра Финли Мрргглтона', en: 'Play Sir Finley Mrrgglton' },
  finleyDetail: { ru: 'Сила героя: смена на «Молнию»', en: 'Hero Power: swap to Lightning Jolt' },
  endTurn: { ru: 'Закончить ход', en: 'End Turn' },
  unknownCard: { ru: 'Сыграть неизвестную карту', en: 'Play Unknown Card' },
  unknownDetail: { ru: 'Новая карта, правил симуляции пока нет', en: 'New card, no simulation rules yet' },
  attack: { ru: 'Атаковать Мурлоком-охотником → герой противника', en: 'Attack with Murloc Tidehunter → Enemy Hero' },
  heroPower: { ru: 'Сила героя', en: 'Hero Power' },
  discover: { ru: 'Сыграть карту с динамическим пулом «Раскопок»', en: 'Play Card With Dynamic Discover Pool' },
  longLabel: {
    ru: 'Сыграть Древнего Невероятно Длинного Имени → дружественный сверхрастянутый приспешник',
    en: 'Play The Ancient One of Unreasonably Long Names → Friendly Hyperextended Minion',
  },
  longDetail: {
    ru: 'Очень длинная строка описания эффекта с выбором и несколькими вложенными условиями выбора цели, которая не должна переполнять панель',
    en: 'A very long detail line describing a choose-one effect with several nested targeting conditions that must not overflow',
  },
  longTrade: { ru: 'Разменять Сверхдлиннорогатый_Приспешник_С_Огромным_Именем', en: 'Trade Supercalifragilisticexpialidocious_Minion_Name' },
  location: { ru: 'Использовать локацию', en: 'Use Location' },
  depUnresolved: { ru: 'Зависимый токен не разрешён', en: 'Dependency token unresolved' },
  poolApprox: { ru: 'Снимок пула приблизительный', en: 'Pool snapshot approximate' },
  engineError: {
    ru: 'Движок отклонил эту позицию. Рекомендации не показаны.',
    en: 'The engine rejected this position. No recommendation is shown.',
  },
} as const

type TextKey = keyof typeof TEXT

export interface FixtureEntry {
  key: string
  name: string
  state: OverlayState
}

export const FIXTURE_KEYS = ['idle', 'thinking', 'exact', 'mixed', 'partial', 'error', 'opponent', 'stress'] as const

export function getFixtures(l: Locale): FixtureEntry[] {
  const x = (k: TextKey) => TEXT[k][l]
  const EXACT = [translate(l, 'summary.exact')]
  const INFERRED = [translate(l, 'summary.inferred'), translate(l, 'note.rulesNotVerified')]
  const NEURAL = [translate(l, 'summary.neural'), translate(l, 'note.noExactChild')]
  const NA = [translate(l, 'summary.unavailable')]

  const exactOnly: Recommendation[] = [
    { id: 'e1', rank: 1, label: x('fireball'), score: 0.67, source: 'EXACT', evidence: EXACT },
    { id: 'e2', rank: 2, label: x('finley'), detail: x('finleyDetail'), score: 0.58, source: 'EXACT', evidence: EXACT },
    { id: 'e3', rank: 3, label: x('endTurn'), score: 0.29, source: 'EXACT', evidence: EXACT },
  ]

  const mixed: Recommendation[] = [
    { id: 'm1', rank: 1, label: x('fireball'), score: 0.67, source: 'EXACT', evidence: EXACT },
    { id: 'm2', rank: 2, label: x('unknownCard'), detail: x('unknownDetail'), score: 0.61, source: 'NEURAL', evidence: NEURAL, fallbackEligible: true },
    { id: 'm3', rank: 3, label: x('attack'), score: 0.54, source: 'INFERRED', evidence: INFERRED },
    { id: 'm4', rank: 4, label: x('endTurn'), score: 0.29, source: 'EXACT', evidence: EXACT },
  ]

  const partial: Recommendation[] = [
    { id: 'p1', rank: 1, label: x('unknownCard'), score: 0.63, source: 'NEURAL', evidence: NEURAL, fallbackEligible: true },
    { id: 'p2', rank: 2, label: x('heroPower'), score: 0.55, source: 'EXACT', evidence: EXACT },
    { id: 'p3', rank: 3, label: x('discover'), source: 'UNAVAILABLE', evidence: NA },
    { id: 'p4', rank: 4, label: x('endTurn'), score: 0.31, source: 'EXACT', evidence: EXACT },
  ]

  const stress: Recommendation[] = [
    {
      id: 's1',
      rank: 1,
      label: x('longLabel'),
      detail: x('longDetail'),
      score: 0.7391,
      source: 'INFERRED',
      evidence: [...INFERRED, x('depUnresolved'), x('poolApprox')],
    },
    { id: 's2', rank: 2, label: x('longTrade'), score: 0.6, source: 'EXACT' },
    { id: 's3', rank: 3, label: x('unknownCard'), source: 'NEURAL', evidence: NEURAL },
    { id: 's4', rank: 4, label: x('location'), source: 'UNAVAILABLE' },
    { id: 's5', rank: 5, label: x('endTurn'), score: 0.12, source: 'EXACT' },
  ]

  const base = { gameId: 'mock-1', activePlayer: 'SELF' as const }

  // idle / thinking / opponent carry no message: those texts belong to the overlay.
  // The error message stands in for a runtime-provided, display-ready string.
  return [
    { key: 'idle', name: 'Idle', state: { turn: 0, activePlayer: 'SELF', status: 'IDLE', recommendations: [] } },
    { key: 'thinking', name: 'Thinking', state: { ...base, turn: 7, status: 'THINKING', recommendations: [] } },
    { key: 'exact', name: 'Exact', state: { ...base, turn: 7, status: 'READY', latencyMs: 182, recommendations: exactOnly } },
    { key: 'mixed', name: 'Mixed', state: { ...base, turn: 7, status: 'READY', latencyMs: 640, recommendations: mixed } },
    { key: 'partial', name: 'Partial', state: { ...base, turn: 7, status: 'READY', latencyMs: 910, recommendations: partial } },
    { key: 'error', name: 'Error', state: { ...base, turn: 7, status: 'ERROR', message: x('engineError'), recommendations: [] } },
    { key: 'opponent', name: 'Opponent', state: { ...base, turn: 6, activePlayer: 'OPPONENT', status: 'READY', recommendations: [] } },
    { key: 'stress', name: 'Stress', state: { ...base, turn: 10, status: 'READY', latencyMs: 1480, recommendations: stress } },
  ]
}
