export type Fixture = {
  id: string
  home_team_id: string
  away_team_id: string
  home_team: string
  away_team: string
  kickoff: string
  venue: string
  stage: string
  status?: string
  score?: { home: number | null; away: number | null; winner?: string | null }
}

export type TeamStatProfile = {
  team_id: string
  team_name: string
  source: string
  matches?: number
  shots?: number
  goals?: number
  xg_for?: number
  passes?: number
  pressures?: number
  goals_against?: number
  wins?: number
  draws?: number
  losses?: number
  points?: number
}

export type FixtureDetail = Fixture & {
  home_team_stats?: TeamStatProfile | null
  away_team_stats?: TeamStatProfile | null
  home_player_features?: Record<string, unknown>
  away_player_features?: Record<string, unknown>
}

export type Edge = {
  model_probability: number
  market_probability: number
  edge: number
  expected_value_per_10: number
  implied_probability: number
  american_odds: number
}

export type Prediction = {
  fixture_id: string
  model_type: string
  model_version: string
  expected_goals: { home: number; away: number }
  wdl: { home: number; draw: number; away: number }
  calibrated_wdl: { home: number; draw: number; away: number }
  top_scores: Array<{ score: string; probability: number }>
  score_matrix: Array<{ score: string; probability: number; home_goals: number | null; away_goals: number | null }>
  raw_score_matrix: Array<{ score: string; probability: number; home_goals: number | null; away_goals: number | null }>
  adjusted_score_matrix: Array<{ score: string; probability: number; home_goals: number | null; away_goals: number | null }>
  confidence: 'low' | 'medium' | 'high'
  data_quality: { level: 'low' | 'medium' | 'high'; score: number; missing: string[]; sources: string[] }
  calibration: { method: string; market_weight: number; wdl: { home: number; draw: number; away: number } }
  risk_flags: string[]
  explanation: string[]
  odds?: { home: number; draw: number; away: number }
  edges?: { home: Edge; draw: Edge; away: Edge }
}

export type BetRecommendation = {
  fixture_id: string
  match: string
  selection: string
  market: string
  model_probability: number
  market_probability: number
  edge: number
  expected_value_per_10: number
  american_odds: number
  confidence: 'low' | 'medium' | 'high'
  source: string
  last_updated?: string | null
}

export type ParlayMode = 'simple' | 'model' | 'aggressive'

export type RecommendedParlay = {
  mode: ParlayMode
  fixture_id?: string
  date?: string
  match?: string
  legs: Array<BetRecommendation | RecommendedParlay>
  combined_probability: number
  decimal_odds: number
  expected_value_per_10: number
  risk_level: 'none' | 'low' | 'medium' | 'high'
  reason: string
  source?: string
}

export type Recommendations = {
  best_singles: BetRecommendation[]
  game_parlays: RecommendedParlay[]
  day_parlays: RecommendedParlay[]
  avoid: Array<{ fixture_id: string; match: string; reason: string }>
  warning: string
}

export type SyncStatus = {
  enabled: boolean
  running: boolean
  last_sync_at?: string | null
  last_success_at?: string | null
  last_error?: string | null
  fixture_source?: string
  odds_source?: string
  current_result_team_profiles?: number
  next_sync_at?: string | null
  stale: boolean
}

export type GroupProjectionTeam = {
  rank: number
  team_id: string
  team_name: string
  points: number
  goal_difference: number
  goals_for: number
  goals_against: number
  wins: number
  draws: number
  losses: number
  qualification: 'qualified' | 'best-third' | 'out'
}

export type BracketMatch = {
  slot: number
  home_team: string
  home_seed: string
  away_team: string
  away_seed: string
  winner: string
  winner_probability: number
  expected_goals: { home: number; away: number }
}

export type TournamentProjection = {
  model_version: string
  group_rankings: Array<{ group: string; teams: GroupProjectionTeam[] }>
  qualifiers_count: number
  bracket: Array<{ round: string; matches: BracketMatch[] }>
  champion: { team_id: string; team_name: string; title_probability: number }
  notes: string[]
}

type ApiEnv = {
  VITE_API_URL?: string
  DEV?: boolean
}

export function resolveApiUrl(env: ApiEnv): string {
  if (env.VITE_API_URL) {
    return env.VITE_API_URL
  }
  return env.DEV ? 'http://127.0.0.1:8000' : ''
}

const API_URL = resolveApiUrl({
  VITE_API_URL: import.meta.env.VITE_API_URL,
  DEV: String(import.meta.env.DEV) === 'true' || import.meta.env.MODE === 'development',
})
export const DASHBOARD_POLL_INTERVAL_MS = 60_000

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${path}`)
  }
  return response.json() as Promise<T>
}
