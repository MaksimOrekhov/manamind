/**
 * Presentation DTOs for the overlay. Frontend-only: not bound to any Python
 * class. A future adapter maps runtime output into these shapes.
 */

/**
 * How a recommendation was evaluated.
 * EXACT       – exactly simulated under the current runtime contract.
 * INFERRED    – simulation completed, but with evidence debt (rules not fully verified).
 * NEURAL      – direct action-value estimate, no exact child state.
 * UNAVAILABLE – no usable recommendation.
 */
export type EvaluationSource = 'EXACT' | 'INFERRED' | 'NEURAL' | 'UNAVAILABLE'

export interface Recommendation {
  id: string
  rank: number
  label: string
  detail?: string
  /** Win probability for SELF in [0, 1]. Absent when unknown; never invented. */
  score?: number
  source: EvaluationSource
  /** Short human-readable evidence notes (not raw internal arrays). */
  evidence?: string[]
  fallbackEligible?: boolean
}

export type OverlayStatus = 'IDLE' | 'THINKING' | 'READY' | 'ERROR'

export interface OverlayState {
  gameId?: string
  turn: number
  activePlayer: 'SELF' | 'OPPONENT'
  status: OverlayStatus
  latencyMs?: number
  /** Player-facing message for IDLE / ERROR states. */
  message?: string
  recommendations: Recommendation[]
}
