import { describe, expect, it } from 'vitest'

import { bracketScoreLabel, qualificationLabel, winnerTone } from '../tournament'

describe('tournament helpers', () => {
  it('formats qualification states for compact group tables', () => {
    expect(qualificationLabel('qualified')).toBe('Auto')
    expect(qualificationLabel('best-third')).toBe('Best 3rd')
    expect(qualificationLabel('out')).toBe('Out')
  })

  it('marks bracket winners by team name', () => {
    expect(winnerTone('France', 'France')).toBe('winner')
    expect(winnerTone('France', 'Brazil')).toBe('challenger')
  })

  it('formats live bracket score metadata', () => {
    expect(bracketScoreLabel({ home: 1, away: 2, winner: 'AWAY_TEAM' }, 'FINISHED')).toBe('FT 1-2')
    expect(bracketScoreLabel({ home: null, away: null }, 'TIMED')).toBe('TIMED')
    expect(bracketScoreLabel(undefined, undefined)).toBe('')
  })
})
