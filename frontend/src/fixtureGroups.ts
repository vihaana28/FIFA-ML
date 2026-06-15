import type { Fixture } from './api'

export type FixtureDateGroup = {
  key: string
  label: string
  sortTime: number
  fixtures: Fixture[]
}

function kickoffDate(value: string): Date | null {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function dateGroupKey(value: string): string {
  const date = kickoffDate(value)
  if (!date) return 'unscheduled'
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function dateGroupLabel(value: string): string {
  const date = kickoffDate(value)
  if (!date) return 'Unscheduled'
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }).format(date)
}

export function kickoffLabel(value: string): string {
  const date = kickoffDate(value)
  if (!date) return 'Unscheduled'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

export function gameTimeLabel(value: string): string {
  const date = kickoffDate(value)
  if (!date) return 'Time TBD'
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

export function groupFixturesByDate(fixtures: Fixture[]): FixtureDateGroup[] {
  const groups = new Map<string, FixtureDateGroup>()

  fixtures.forEach((fixture) => {
    const date = kickoffDate(fixture.kickoff)
    const key = dateGroupKey(fixture.kickoff)
    const group = groups.get(key) ?? {
      key,
      label: dateGroupLabel(fixture.kickoff),
      sortTime: date?.getTime() ?? Number.MAX_SAFE_INTEGER,
      fixtures: [],
    }
    group.fixtures.push(fixture)
    groups.set(key, group)
  })

  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      fixtures: [...group.fixtures].sort((first, second) => {
        const firstTime = kickoffDate(first.kickoff)?.getTime() ?? Number.MAX_SAFE_INTEGER
        const secondTime = kickoffDate(second.kickoff)?.getTime() ?? Number.MAX_SAFE_INTEGER
        return firstTime - secondTime
      }),
    }))
    .sort((first, second) => first.sortTime - second.sortTime)
}
