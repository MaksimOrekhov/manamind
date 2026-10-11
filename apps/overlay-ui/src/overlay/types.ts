export type Language = 'ru' | 'en'
export interface Instruction { verb: string; source: string; target: string; placement: string; warning: string }
export interface Recommendation {
  rank: number
  action: Record<string, string | number | boolean | null>
  logit: number
  view: Record<Language, Instruction>
}
export type Status = 'DISCONNECTED' | 'WAITING_FOR_GAME' | 'SYNCING' | 'READY' | 'UNTRUSTED' | 'GAME_OVER' | 'THINKING' | 'UNAVAILABLE'
export interface Preferences { language: Language; opacity: number; collapsed: boolean }
export interface Frame {
  schema: 'manamind.overlay/1'; session: string; revision: number; status: Status
  reason: string | null; turn: number | null; generated_at: string | null
  policy_available?: boolean
  recommendations: Recommendation[]; preferences?: Preferences
}
export interface DesktopApi {
  get_frame(): Promise<Frame>
  set_preferences(value: Preferences): Promise<Preferences>
  close(): Promise<void>
}
declare global { interface Window { pywebview?: { api: DesktopApi } } }
