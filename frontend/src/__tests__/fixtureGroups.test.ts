import { describe, expect, it } from 'vitest'

import type { Fixture } from '../api'
import { dateGroupKey, gameTimeLabel, groupFixturesByDate } from '../fixtureGroups'

const fixture = (id: string, kickoff: string, home = id): Fixture => ({
  id,
  home_team_id: `${id}-home`,
  away_team_id: `${id}-away`,
  home_team: home,
  away_team: `${home} Away`,
  kickoff,
  venue: 'Test Stadium',
  stage: 'Group',
})

describe('fixture date grouping', () => {
  it('groups fixtures by local kickoff date and sorts groups and games by kickoff time', () => {
    const groups = groupFixturesByDate([
      fixture('late', '2026-06-12T22:00:00Z', 'Late'),
      fixture('next-day', '2026-06-13T18:00:00Z', 'Next Day'),
      fixture('early', '2026-06-12T18:00:00Z', 'Early'),
    ])

    expect(groups).toHaveLength(2)
    expect(groups[0].fixtures.map((item) => item.id)).toEqual(['early', 'late'])
    expect(groups[1].fixtures.map((item) => item.id)).toEqual(['next-day'])
  })

  it('puts invalid kickoff values in an unscheduled group', () => {
    const groups = groupFixturesByDate([fixture('bad-date', 'not-a-date')])

    expect(groups[0].key).toBe('unscheduled')
    expect(groups[0].label).toBe('Unscheduled')
    expect(dateGroupKey('not-a-date')).toBe('unscheduled')
    expect(gameTimeLabel('not-a-date')).toBe('Time TBD')
  })
})
