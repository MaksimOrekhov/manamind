import type { Frame } from './types'

export const emptyFrame = (): Frame => ({ schema: 'manamind.overlay/1', session: '', revision: -1,
  status: 'DISCONNECTED', reason: null, turn: null, generated_at: null, recommendations: [] })

/** A reload starts empty. Never replay an older revision or advice from a previous process. */
export function acceptFrame(current: Frame, next: Frame): Frame {
  if (next.schema !== 'manamind.overlay/1') return emptyFrame()
  if (next.session === current.session && next.revision < current.revision) return current
  return { ...next, recommendations: next.status === 'READY' ? next.recommendations : [] }
}

export function disconnected(current: Frame): Frame {
  return { ...current, status: 'DISCONNECTED', reason: 'BRIDGE_DISCONNECTED', turn: null,
    generated_at: null, recommendations: [] }
}
