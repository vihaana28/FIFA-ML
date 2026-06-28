import { describe, expect, it } from 'vitest'

import {
  formatPercent,
  parlaySummary,
  recommendationSummary,
  recommendedParlayLegDetails,
  recommendedParlayPickLines,
  strongestEdge,
  syncStatusSummary,
  teamStatSummary,
} from '../betting'

describe('betting UI helpers', () => {
  it('formats percentages for probability displays', () => {
    expect(formatPercent(0.6154)).toBe('61.5%')
  })

  it('finds the strongest positive edge', () => {
    const edge = strongestEdge({
      home: { edge: 0.08, expected_value_per_10: 1.2 },
      draw: { edge: -0.04, expected_value_per_10: -0.7 },
      away: { edge: 0.03, expected_value_per_10: 0.4 },
    })

    expect(edge?.outcome).toBe('home')
  })

  it('summarizes parlay probability from independent legs', () => {
    const summary = parlaySummary([
      { label: 'USA', probability: 0.6, american_odds: -110 },
      { label: 'Brazil', probability: 0.7, american_odds: -150 },
    ])

    expect(summary.combinedProbability).toBeCloseTo(0.42)
    expect(summary.decimalOdds).toBeGreaterThan(3)
  })

  it('summarizes recommendation sections for the bottom panel', () => {
    const summary = recommendationSummary({
      best_singles: [{ edge: 0.052, expected_value_per_10: 1.44 }],
      game_parlays: [
        {
          mode: 'simple',
          fixture_id: 'game-1',
          match: 'A vs B',
          legs: [],
          combined_probability: 0.54,
          decimal_odds: 2.1,
          expected_value_per_10: 1.2,
          risk_level: 'low',
          reason: 'Positive EV moneyline pick.',
        },
      ],
      day_parlays: [
        {
          mode: 'simple',
          date: '2026-06-12',
          legs: [],
          combined_probability: 0.31,
          decimal_odds: 4.2,
          expected_value_per_10: 2.1,
          risk_level: 'medium',
          reason: 'Positive EV day parlay.',
        },
      ],
      avoid: [{ reason: 'No real moneyline odds available.' }, { reason: 'No positive EV edge above threshold.' }],
      warning: 'Strategy simulator only.',
    })

    expect(summary.bestEdge).toBe('5.2%')
    expect(summary.singleCount).toBe(1)
    expect(summary.gameParlayCount).toBe(1)
    expect(summary.dayParlayCount).toBe(1)
    expect(summary.avoidCount).toBe(2)
  })

  it('formats exact parlay pick details', () => {
    expect(
      recommendedParlayLegDetails({
        fixture_id: 'game-1',
        match: 'England vs Croatia',
        selection: 'England',
        market: 'moneyline',
        model_probability: 0.563,
        market_probability: 0.481,
        edge: 0.082,
        expected_value_per_10: 2.05,
        american_odds: 120,
        confidence: 'high',
        source: 'test-book',
      }),
    ).toBe('England vs Croatia - England moneyline, +120, 56.3% model, 48.1% market, +8.2% edge, $2.05 EV/$10')
  })

  it('flattens nested day parlay picks into exact leg lines', () => {
    const lines = recommendedParlayPickLines({
      mode: 'simple',
      date: '2026-06-17',
      legs: [
        {
          mode: 'simple',
          fixture_id: 'game-1',
          match: 'England vs Croatia',
          legs: [
            {
              fixture_id: 'game-1',
              match: 'England vs Croatia',
              selection: 'England',
              market: 'moneyline',
              model_probability: 0.563,
              market_probability: 0.481,
              edge: 0.082,
              expected_value_per_10: 2.05,
              american_odds: 120,
              confidence: 'high',
              source: 'test-book',
            },
          ],
          combined_probability: 0.563,
          decimal_odds: 2.2,
          expected_value_per_10: 2.05,
          risk_level: 'low',
          reason: 'Positive EV moneyline pick.',
        },
      ],
      combined_probability: 0.563,
      decimal_odds: 2.2,
      expected_value_per_10: 2.05,
      risk_level: 'medium',
      reason: 'Positive EV day parlay.',
    })

    expect(lines).toEqual([
      'England vs Croatia - England moneyline, +120, 56.3% model, 48.1% market, +8.2% edge, $2.05 EV/$10',
    ])
  })

  it('summarizes team stats for match detail cards', () => {
    const summary = teamStatSummary({ matches: 7, shots: 92, xg_for: 11.6, goals: 10, source: 'StatsBomb Open Data' })

    expect(summary).toEqual({
      source: 'StatsBomb Open Data',
      matches: '7',
      xgPerMatch: '1.66',
      shotsPerMatch: '13.1',
      goalsPerMatch: '1.43',
      record: '0-0-0',
      points: '0 pts',
      goalsAgainst: '0 GA',
    })
  })

  it('summarizes auto-sync status for the dashboard', () => {
    expect(syncStatusSummary({ enabled: true, stale: false, last_success_at: '2026-06-13T20:00:00Z' }).label).toContain('Auto-sync on')
    expect(syncStatusSummary({ enabled: true, stale: true, last_error: 'quota exceeded' }).tone).toBe('stale')
    expect(syncStatusSummary({ enabled: false, stale: false }).label).toBe('Auto-sync off')
  })
})
