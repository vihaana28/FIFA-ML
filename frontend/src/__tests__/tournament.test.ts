import { describe, expect, it } from 'vitest'

import { qualificationLabel, winnerTone } from '../tournament'

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
})
