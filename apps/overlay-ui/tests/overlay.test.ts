import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { countSources, formatScore, sortByRank } from '../src/overlay/format'
import { FIXTURES } from '../src/overlay/fixtures'
import EvaluationBadge from '../src/components/EvaluationBadge.vue'
import OverlayPanel from '../src/components/OverlayPanel.vue'
import RecommendationItem from '../src/components/RecommendationItem.vue'
import type { OverlayState } from '../src/overlay/types'

const fixture = (key: string): OverlayState => FIXTURES.find((f) => f.key === key)!.state

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

describe('EvaluationBadge', () => {
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

describe('OverlayPanel', () => {
  it('renders recommendations in rank order', () => {
    const state = fixture('mixed')
    const w = mount(OverlayPanel, {
      props: { state: { ...state, recommendations: [...state.recommendations].reverse() } },
    })
    expect(w.findAll('[data-testid=rank]').map((n) => n.text())).toEqual(['1', '2', '3', '4'])
  })
  it('shows a message and no list for idle, thinking, error and opponent turn', () => {
    for (const key of ['idle', 'thinking', 'error', 'opponent']) {
      const w = mount(OverlayPanel, { props: { state: fixture(key) } })
      expect(w.find('ol').exists()).toBe(false)
      expect(w.text()).toContain(fixture(key).message!)
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
