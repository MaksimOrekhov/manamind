import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { STORAGE_KEY, initLocale, locale, setLocale, type Locale } from '../src/i18n'
import { countSources, formatScore, sortByRank } from '../src/overlay/format'
import { getFixtures } from '../src/overlay/fixtures'
import EvaluationBadge from '../src/components/EvaluationBadge.vue'
import OverlayHeader from '../src/components/OverlayHeader.vue'
import OverlayPanel from '../src/components/OverlayPanel.vue'
import RecommendationItem from '../src/components/RecommendationItem.vue'
import type { OverlayState } from '../src/overlay/types'

const fixture = (key: string, l: Locale = 'en'): OverlayState => getFixtures(l).find((f) => f.key === key)!.state

beforeEach(() => {
  localStorage.clear()
  initLocale()
  setLocale('en')
  localStorage.clear()
})

describe('formatScore', () => {
  it('rounds to a whole percent', () => {
    expect(formatScore(0.6739421)).toBe('67%')
    expect(formatScore(0)).toBe('0%')
    expect(formatScore(1)).toBe('100%')
  })
  it('shows an em dash when the score is missing', () => {
    expect(formatScore(undefined)).toBe('—')
    expect(formatScore(Number.NaN)).toBe('—')
  })
})

describe('EvaluationBadge (en)', () => {
  it.each([
    ['EXACT', 'EXACT', '●'],
    ['INFERRED', 'INFERRED', '◐'],
    ['NEURAL', 'NEURAL', '◆'],
    ['UNAVAILABLE', 'N/A', '✕'],
  ] as const)('renders %s with text and icon', (source, label, icon) => {
    const w = mount(EvaluationBadge, { props: { source } })
    expect(w.text()).toContain(label)
    expect(w.text()).toContain(icon)
  })
  it('does not call INFERRED or NEURAL exact', () => {
    expect(mount(EvaluationBadge, { props: { source: 'INFERRED' } }).text()).not.toContain('EXACT')
    expect(mount(EvaluationBadge, { props: { source: 'NEURAL' } }).text()).not.toContain('EXACT')
  })
})

describe('RecommendationItem', () => {
  it('shows a dash for a missing score and no invented number', () => {
    const w = mount(RecommendationItem, {
      props: { rec: { id: 'x', rank: 3, label: 'Use Location', source: 'UNAVAILABLE' } },
    })
    expect(w.get('[data-testid=score]').text()).toBe('—')
  })
  it('expands details with the keyboard-reachable button', async () => {
    const w = mount(RecommendationItem, { props: { rec: fixture('mixed').recommendations[2] } })
    expect(w.find('[data-testid=details]').exists()).toBe(false)
    await w.get('button').trigger('click')
    expect(w.get('button').attributes('aria-expanded')).toBe('true')
    expect(w.get('[data-testid=details]').text()).toContain('evidence debt')
  })
})

describe('fixtures', () => {
  it('mixed fixture has exact, inferred and neural sources', () => {
    const counts = countSources(fixture('mixed').recommendations)
    expect(counts).toMatchObject({ EXACT: 2, INFERRED: 1, NEURAL: 1, UNAVAILABLE: 0 })
  })
  it('partial fixture contains an unavailable recommendation without a score', () => {
    const na = fixture('partial').recommendations.filter((r) => r.source === 'UNAVAILABLE')
    expect(na.length).toBeGreaterThan(0)
    expect(na.every((r) => r.score === undefined)).toBe(true)
  })
  it('sorts by rank regardless of input order', () => {
    const shuffled = [...fixture('stress').recommendations].reverse()
    expect(sortByRank(shuffled).map((r) => r.rank)).toEqual([1, 2, 3, 4, 5])
  })
})

describe('OverlayPanel (en)', () => {
  it('renders recommendations in rank order', () => {
    const state = fixture('mixed')
    const w = mount(OverlayPanel, {
      props: { state: { ...state, recommendations: [...state.recommendations].reverse() } },
    })
    expect(w.findAll('[data-testid=rank]').map((n) => n.text())).toEqual(['1', '2', '3', '4'])
  })
  it('shows a message and no list for idle, thinking, error and opponent turn', () => {
    const expected = {
      idle: 'No active Hearthstone match',
      thinking: 'Analyzing position…',
      error: 'No recommendation is shown',
      opponent: 'Waiting for opponent…',
    }
    for (const [key, text] of Object.entries(expected)) {
      const w = mount(OverlayPanel, { props: { state: fixture(key) } })
      expect(w.find('ol').exists()).toBe(false)
      expect(w.text()).toContain(text)
    }
  })
  it('summarises sources in the footer', () => {
    const w = mount(OverlayPanel, { props: { state: fixture('mixed') } })
    const foot = w.get('footer').text()
    expect(foot).toContain('Exact 2')
    expect(foot).toContain('Inferred 1')
    expect(foot).toContain('Neural 1')
  })
})

describe('localization', () => {
  it('defaults to Russian when nothing is stored', () => {
    localStorage.clear()
    initLocale()
    expect(locale.value).toBe('ru')
    expect(document.documentElement.lang).toBe('ru')
  })

  it('switches to English via the header and persists the choice', async () => {
    initLocale()
    const w = mount(OverlayHeader, { props: { state: fixture('exact') } })
    expect(w.text()).toContain('Ход 7')
    const en = w.findAll('button').find((b) => b.text() === 'EN')!
    await en.trigger('click')
    expect(locale.value).toBe('en')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('en')
    expect(w.text()).toContain('Turn 7')
    expect(en.attributes('aria-pressed')).toBe('true')
  })

  it('restores a persisted locale and ignores invalid values', () => {
    localStorage.setItem(STORAGE_KEY, 'en')
    initLocale()
    expect(locale.value).toBe('en')
    localStorage.setItem(STORAGE_KEY, 'de')
    initLocale()
    expect(locale.value).toBe('ru')
  })

  it('renders Russian badges: EXACT -> ТОЧНО, NEURAL -> НЕЙРО', () => {
    setLocale('ru')
    expect(mount(EvaluationBadge, { props: { source: 'EXACT' } }).text()).toContain('ТОЧНО')
    expect(mount(EvaluationBadge, { props: { source: 'NEURAL' } }).text()).toContain('НЕЙРО')
    expect(mount(EvaluationBadge, { props: { source: 'INFERRED' } }).text()).toContain('ПРЕДПОЛ.')
    expect(mount(EvaluationBadge, { props: { source: 'UNAVAILABLE' } }).text()).toContain('Н/Д')
    expect(mount(EvaluationBadge, { props: { source: 'EXACT' } }).attributes('title')).toBe('Точный расчёт движком')
  })

  it('translates statuses and overlay-owned messages', () => {
    setLocale('ru')
    const expected = {
      idle: ['Ожидание', 'Нет активного матча Hearthstone'],
      thinking: ['Анализ', 'Анализирую позицию…'],
      opponent: ['Ждём', 'Ожидание хода соперника…'],
      error: ['Ошибка', 'Движок отклонил эту позицию'],
    }
    for (const [key, [status, message]] of Object.entries(expected)) {
      const text = mount(OverlayPanel, { props: { state: fixture(key, 'ru') } }).text()
      expect(text).toContain(status)
      expect(text).toContain(message)
    }
    const ready = mount(OverlayPanel, { props: { state: fixture('mixed', 'ru') } }).text()
    expect(ready).toContain('Готово')
    expect(ready).toContain('Ход 7')
    expect(ready).toContain('640 мс')
    expect(ready).toContain('Закончить ход')
    expect(ready).toContain('Нейро 1')
  })

  it('switching language does not change score, rank or source semantics', async () => {
    const state = fixture('mixed')
    const w = mount(OverlayPanel, { props: { state } })
    const snapshot = () => ({
      ranks: w.findAll('[data-testid=rank]').map((n) => n.text()),
      scores: w.findAll('[data-testid=score]').map((n) => n.text()),
      icons: w.findAll('[data-testid=source-badge]').map((n) => n.get('.badge__icon').text()),
      classes: w.findAll('[data-testid=source-badge]').map((n) => n.classes().find((c) => c !== 'badge')),
    })
    const before = snapshot()
    setLocale('ru')
    await w.vm.$nextTick()
    expect(w.findAll('[data-testid=source-badge] .badge__label').map((n) => n.text())).toContain('НЕЙРО')
    expect(snapshot()).toEqual(before)
    expect(before.scores).toEqual(['67%', '61%', '54%', '29%'])
  })

  it('missing score stays a dash in Russian', () => {
    setLocale('ru')
    const w = mount(RecommendationItem, {
      props: { rec: { id: 'x', rank: 3, label: 'Использовать локацию', source: 'UNAVAILABLE' } },
    })
    expect(w.get('[data-testid=score]').text()).toBe('—')
    expect(w.text()).toContain('Н/Д')
  })
})
