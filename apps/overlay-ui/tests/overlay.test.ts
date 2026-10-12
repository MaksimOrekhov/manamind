import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../src/App.vue'
import OverlayPanel from '../src/components/OverlayPanel.vue'
import { acceptFrame, disconnected, emptyFrame } from '../src/overlay/feed'
import type { Frame } from '../src/overlay/types'

const ready = (): Frame => ({ ...emptyFrame(), session: 'session', revision: 3, status: 'READY', turn: 7,
  generated_at: '2026-10-11T10:20:30Z', recommendations: [1,2,3].map(rank => ({rank, logit: 7.5 - rank,
    action: { type: 'PLAY_CARD', hand_index: 3, target_side: 'OPPONENT', card_id: 'TECHNICAL_CARD_ID' },
    ...(rank === 1 ? { risk_warning: { ru: 'Внимание: действие может усилить существо противника.', en: 'Warning: this action may help an enemy minion.' } } : {}),
    view: { ru: { verb: 'РАЗЫГРАТЬ', source: 'ИЗ РУКИ: Быстрое исцеление · 4-я карта слева', target: 'ГЕРОЙ ПРОТИВНИКА', placement: '', warning: '' },
      en: { verb: 'PLAY', source: 'FROM HAND: Flash Heal · card 4 from left', target: 'ENEMY HERO', placement: '', warning: '' } } })) })

describe('real overlay DTO presentation', () => {
  it('keeps Policy order, target and side; highlights only Top-1 and hides logits/IDs in details', () => {
    const panel = mount(OverlayPanel, {props:{frame:ready(), language:'ru'}})
    expect(panel.findAll('.item').map(item=>item.find('.item__rank').text())).toEqual(['1','2','3'])
    expect(panel.findAll('.item--top')).toHaveLength(1)
    expect(panel.find('.item__source').text()).toContain('4-я карта слева')
    expect(panel.find('.item__target').text()).toContain('ГЕРОЙ ПРОТИВНИКА')
    expect(panel.find('.item__source').text()).not.toContain('TECHNICAL_CARD_ID')
    expect(panel.findAll('.item__risk-warning')).toHaveLength(1)
    expect(panel.find('.item__risk-warning').text()).toContain('усилить существо противника')
    expect(panel.find('details').text()).toContain('не вероятность победы')
    expect(panel.text()).not.toContain('EXACT')
  })
  it('switches names and instructions to English without changing actions', async () => {
    const panel = mount(OverlayPanel,{props:{frame:ready(),language:'ru'}})
    await panel.setProps({language:'en'})
    expect(panel.find('.item__source').text()).toContain('Flash Heal')
    expect(panel.find('.item__target').text()).toContain('ENEMY HERO')
    expect(panel.find('.item__risk-warning').text()).toContain('may help an enemy minion')
  })
  for (const status of ['SYNCING','UNTRUSTED','GAME_OVER','DISCONNECTED','THINKING','UNAVAILABLE'] as const) {
    it(`clears all advice in ${status}, even if the payload carries an old list`,()=>{
      const frame = acceptFrame(ready(),{...ready(),revision:4,status})
      expect(frame.recommendations).toHaveLength(0)
      const panel=mount(OverlayPanel,{props:{frame,language:'ru'}})
      expect(panel.findAll('.item')).toHaveLength(0)
    })
  }
  it('discards old revisions and resets on process replacement / connection loss',()=>{
    expect(acceptFrame(ready(),{...ready(),revision:2})).toEqual(ready())
    expect(acceptFrame(ready(),{...emptyFrame(),session:'new',revision:0}).recommendations).toHaveLength(0)
    expect(disconnected(ready()).recommendations).toHaveLength(0)
    expect(acceptFrame(emptyFrame(),{...emptyFrame(),session:'new'}).recommendations).toHaveLength(0)
  })
  it('hides advice on bridge failure and discards a late response after timeout', async()=>{
    vi.useFakeTimers()
    let resolveOld: (value: Frame) => void = () => {}
    const getFrame = vi.fn().mockResolvedValueOnce(ready())
      .mockImplementationOnce(() => new Promise<Frame>(resolve => { resolveOld = resolve }))
      .mockResolvedValue({...emptyFrame(),session:'session',revision:4,status:'SYNCING'})
    window.pywebview = {api:{get_frame:getFrame,set_preferences:vi.fn(),flag_suspicious:vi.fn().mockResolvedValue({status:'SAVED'}),close:vi.fn()}}
    const app=mount(App)
    await flushPromises()
    expect(app.findAll('.item')).toHaveLength(3)
    await vi.advanceTimersByTimeAsync(2500)
    expect(app.findAll('.item')).toHaveLength(0)
    resolveOld(ready())
    await flushPromises()
    expect(app.findAll('.item')).toHaveLength(0)
    app.unmount(); delete window.pywebview; vi.useRealTimers()
  })
  it('keeps a missing checkpoint warning while the log is disconnected',()=>{
    const panel=mount(OverlayPanel,{props:{frame:{...emptyFrame(),policy_available:false},language:'ru'}})
    expect(panel.find('.policy-error').text()).toContain('Policy не загрузилась')
  })
  it('marks the currently displayed decision once and clears the mark when it changes', async()=>{
    const flag = vi.fn().mockResolvedValue({status:'SAVED'})
    window.pywebview = {api:{get_frame:vi.fn(),set_preferences:vi.fn(),flag_suspicious:flag,close:vi.fn()}}
    const panel=mount(OverlayPanel,{props:{frame:ready(),language:'ru'}})
    expect(panel.get('.feedback-flag').text()).toContain('кажется сомнительной')
    expect(panel.find('.waiting').exists()).toBe(false)
    expect(panel.findAll('.item')).toHaveLength(3)
    await panel.get('.feedback-flag').trigger('click')
    await flushPromises()
    expect(flag).toHaveBeenCalledWith({session:'session',revision:3})
    expect(panel.get('.feedback-flag').text()).toContain('Отмечено')
    expect((panel.get('.feedback-flag').element as HTMLButtonElement).disabled).toBe(true)
    expect(panel.find('.feedback-message').exists()).toBe(true)
    expect(panel.find('.waiting').exists()).toBe(false)
    expect(panel.findAll('.item')).toHaveLength(3)
    await panel.setProps({frame:{...ready(),revision:4}})
    expect(panel.get('.feedback-flag').text()).toContain('кажется сомнительной')
    expect((panel.get('.feedback-flag').element as HTMLButtonElement).disabled).toBe(false)
    panel.unmount(); delete window.pywebview
  })
  it('clears a saved flag when the LIVE session changes but revision stays the same', async()=>{
    window.pywebview = {api:{get_frame:vi.fn(),set_preferences:vi.fn(),
      flag_suspicious:vi.fn().mockResolvedValue({status:'SAVED'}),close:vi.fn()}}
    const panel=mount(OverlayPanel,{props:{frame:ready(),language:'ru'}})
    await panel.get('.feedback-flag').trigger('click')
    await flushPromises()
    expect((panel.get('.feedback-flag').element as HTMLButtonElement).disabled).toBe(true)
    await panel.setProps({frame:{...ready(),session:'replacement-session'}})
    expect(panel.get('.feedback-flag').text()).toContain('кажется сомнительной')
    expect((panel.get('.feedback-flag').element as HTMLButtonElement).disabled).toBe(false)
    expect(panel.find('.feedback-message').exists()).toBe(false)
    expect(panel.findAll('.item')).toHaveLength(3)
    panel.unmount(); delete window.pywebview
  })
  it('shows waiting state and hides feedback when LIVE disconnects', async()=>{
    window.pywebview = {api:{get_frame:vi.fn(),set_preferences:vi.fn(),
      flag_suspicious:vi.fn().mockResolvedValue({status:'SAVED'}),close:vi.fn()}}
    const panel=mount(OverlayPanel,{props:{frame:ready(),language:'ru'}})
    await panel.get('.feedback-flag').trigger('click')
    await flushPromises()
    await panel.setProps({frame:{...ready(),revision:4,status:'DISCONNECTED',recommendations:[]}})
    expect(panel.findAll('.item')).toHaveLength(0)
    expect(panel.find('.feedback-flag').exists()).toBe(false)
    expect(panel.find('.feedback-message').exists()).toBe(false)
    expect(panel.find('.waiting').exists()).toBe(true)
    panel.unmount(); delete window.pywebview
  })
  it('explains when a click raced with a changed LIVE decision', async()=>{
    window.pywebview = {api:{get_frame:vi.fn(),set_preferences:vi.fn(),
      flag_suspicious:vi.fn().mockResolvedValue({status:'STALE'}),close:vi.fn()}}
    const panel=mount(OverlayPanel,{props:{frame:ready(),language:'ru'}})
    await panel.get('.feedback-flag').trigger('click')
    await flushPromises()
    expect(panel.find('.feedback-message').text()).toContain('Решение уже изменилось')
    panel.unmount(); delete window.pywebview
  })
})
