import type { BetRecommendation, RecommendedParlay } from './api'

type EdgeRecord = Record<string, { edge: number; expected_value_per_10: number }>

export type ParlayLeg = {
  label: string
  probability: number
  american_odds: number
}

type RecommendationPayload = {
  best_singles: Array<{ edge: number; expected_value_per_10: number }>
  game_parlays: Array<{ combined_probability: number; [key: string]: unknown }>
  day_parlays: Array<{ combined_probability: number; [key: string]: unknown }>
  avoid: Array<{ reason: string }>
  warning: string
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function americanToDecimal(americanOdds: number): number {
  return americanOdds > 0 ? 1 + americanOdds / 100 : 1 + 100 / Math.abs(americanOdds)
}

export function strongestEdge(edges: EdgeRecord): { outcome: string; edge: number; expectedValue: number } | null {
  const ranked = Object.entries(edges)
    .map(([outcome, value]) => ({ outcome, edge: value.edge, expectedValue: value.expected_value_per_10 }))
    .filter((value) => value.edge > 0)
    .sort((a, b) => b.edge - a.edge)

  return ranked[0] ?? null
}

export function parlaySummary(legs: ParlayLeg[]): { combinedProbability: number; decimalOdds: number; expectedValuePer10: number } {
  const combinedProbability = legs.reduce((value, leg) => value * leg.probability, 1)
  const decimalOdds = legs.reduce((value, leg) => value * americanToDecimal(leg.american_odds), 1)
  const profit = 10 * decimalOdds - 10
  return {
    combinedProbability,
    decimalOdds,
    expectedValuePer10: combinedProbability * profit - (1 - combinedProbability) * 10,
  }
}

export function recommendationSummary(recommendations: RecommendationPayload): {
  singleCount: number
  gameParlayCount: number
  dayParlayCount: number
  avoidCount: number
  bestEdge: string
} {
  const best = [...recommendations.best_singles].sort((a, b) => b.edge - a.edge)[0]
  return {
    singleCount: recommendations.best_singles.length,
    gameParlayCount: recommendations.game_parlays.length,
    dayParlayCount: recommendations.day_parlays.length,
    avoidCount: recommendations.avoid.length,
    bestEdge: best ? formatPercent(best.edge) : '0.0%',
  }
}

function signedNumber(value: number, decimals: number, suffix = ''): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(decimals)}${suffix}`
}

function americanOddsLabel(value: number): string {
  return value > 0 ? `+${value}` : String(value)
}

function marketLabel(value: string): string {
  return value.replaceAll('_', ' ')
}

function isBetRecommendation(value: BetRecommendation | RecommendedParlay): value is BetRecommendation {
  return 'selection' in value
}

export function recommendedParlayLegDetails(leg: BetRecommendation): string {
  return [
    `${leg.match} - ${leg.selection} ${marketLabel(leg.market)}`,
    americanOddsLabel(leg.american_odds),
    `${formatPercent(leg.model_probability)} model`,
    `${formatPercent(leg.market_probability)} market`,
    `${signedNumber(leg.edge * 100, 1, '%')} edge`,
    `$${leg.expected_value_per_10.toFixed(2)} EV/$10`,
  ].join(', ')
}

export function recommendedParlayPickLines(parlay: RecommendedParlay): string[] {
  return parlay.legs.flatMap((leg) => {
    if (isBetRecommendation(leg)) {
      return [recommendedParlayLegDetails(leg)]
    }
    const nested = recommendedParlayPickLines(leg)
    return nested.length > 0 ? nested : [`${leg.match ?? leg.date ?? 'Game parlay'} - ${leg.reason}`]
  })
}

export function teamStatSummary(stats?: {
  matches?: number
  shots?: number
  xg_for?: number
  goals?: number
  goals_against?: number
  wins?: number
  draws?: number
  losses?: number
  points?: number
  source?: string
} | null): {
  source: string
  matches: string
  xgPerMatch: string
  shotsPerMatch: string
  goalsPerMatch: string
  record: string
  points: string
  goalsAgainst: string
} {
  const matches = Math.max(1, stats?.matches ?? 0)
  return {
    source: stats?.source ?? 'No stat source yet',
    matches: String(stats?.matches ?? 0),
    xgPerMatch: (((stats?.xg_for ?? 0) / matches)).toFixed(2),
    shotsPerMatch: (((stats?.shots ?? 0) / matches)).toFixed(1),
    goalsPerMatch: (((stats?.goals ?? 0) / matches)).toFixed(2),
    record: `${stats?.wins ?? 0}-${stats?.draws ?? 0}-${stats?.losses ?? 0}`,
    points: `${stats?.points ?? 0} pts`,
    goalsAgainst: `${stats?.goals_against ?? 0} GA`,
  }
}

export function syncStatusSummary(status?: {
  enabled: boolean
  stale: boolean
  running?: boolean
  last_success_at?: string | null
  last_error?: string | null
} | null): { label: string; detail: string; tone: 'ok' | 'stale' | 'off' | 'running' } {
  if (!status || !status.enabled) {
    return { label: 'Auto-sync off', detail: 'Manual refresh only', tone: 'off' }
  }
  if (status.running) {
    return { label: 'Auto-sync running', detail: 'Refreshing scores', tone: 'running' }
  }
  if (status.stale) {
    return { label: 'Data stale', detail: status.last_error ?? 'Last sync failed', tone: 'stale' }
  }
  const updated = status.last_success_at ? new Date(status.last_success_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : 'waiting'
  return { label: `Auto-sync on / Last updated ${updated}`, detail: 'Local DB refreshes every minute', tone: 'ok' }
}
