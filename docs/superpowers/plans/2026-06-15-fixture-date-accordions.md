# Fixture Date Accordions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the Games rail by kickoff date with collapsed date dropdowns.

**Architecture:** Keep the change frontend-only. `frontend/src/fixtureGroups.ts` derives date groups from existing `Fixture.kickoff` and exposes formatting helpers. `frontend/src/App.tsx` tracks open date groups locally, renders accordions, and opens the selected game's date. `frontend/src/styles.css` adds compact accordion styling that matches the current rail.

**Tech Stack:** React 19, TypeScript, Vite, lucide-react.

---

## File Structure

- Create `frontend/src/fixtureGroups.ts`: date parsing, date key/label formatting, time formatting, and fixture grouping.
- Create `frontend/src/__tests__/fixtureGroups.test.ts`: verifies grouping, sorting, and invalid kickoff fallback.
- Modify `frontend/src/App.tsx`: add accordion open state, grouped fixture rendering, and chevron icons.
- Modify `frontend/src/styles.css`: add date group/header styles and nested game spacing.

---

### Task 1: Date Accordion Games Rail

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing fixture grouping test**

Create `frontend/src/__tests__/fixtureGroups.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
cd frontend
npm test -- fixtureGroups
```

Expected: FAIL because `../fixtureGroups` does not exist.

- [ ] **Step 3: Add date grouping helper module**

Create `frontend/src/fixtureGroups.ts`:

```ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
cd frontend
npm test -- fixtureGroups
```

Expected: PASS.

- [ ] **Step 5: Wire date accordions in `frontend/src/App.tsx`**

Add `ChevronDown` and `ChevronRight` to the existing lucide import:

```ts
import { Activity, AlertTriangle, BarChart3, ChevronDown, ChevronRight, Plus, RefreshCcw, Target, Trophy } from 'lucide-react'
```

Add this import below existing local imports:

```ts
import { dateGroupKey, gameTimeLabel, groupFixturesByDate, kickoffLabel } from './fixtureGroups'
```

Remove the local `kickoffLabel` helper from `App.tsx`.

- [ ] **Step 2: Add open group state and grouped fixture memo**

Inside `App`, after `selectedId` state:

```ts
const [openDateGroups, setOpenDateGroups] = useState<Record<string, boolean>>({})
```

After `matrixCells`:

```ts
const fixtureDateGroups = useMemo(() => groupFixturesByDate(fixtures), [fixtures])

useEffect(() => {
  const selected = fixtures.find((fixture) => fixture.id === selectedId)
  if (!selected) return
  const key = dateGroupKey(selected.kickoff)
  setOpenDateGroups((current) => (current[key] ? current : { ...current, [key]: true }))
}, [fixtures, selectedId])
```

Add toggle helper before `addLeg`:

```ts
function toggleDateGroup(key: string) {
  setOpenDateGroups((current) => ({ ...current, [key]: !current[key] }))
}
```

- [ ] **Step 6: Replace flat fixture rendering with date groups**

Replace:

```tsx
{fixtures.map((fixture) => (
  <button
    className={`fixture-button ${fixture.id === selectedId ? 'active' : ''}`}
    key={fixture.id}
    onClick={() => setSelectedId(fixture.id)}
  >
    <span>{fixture.home_team}</span>
    <strong>vs</strong>
    <span>{fixture.away_team}</span>
    <small>{kickoffLabel(fixture.kickoff)} / {fixture.venue}</small>
  </button>
))}
```

With:

```tsx
{fixtureDateGroups.map((group) => {
  const isOpen = Boolean(openDateGroups[group.key])
  return (
    <div className="date-group" key={group.key}>
      <button
        className="date-group-toggle"
        type="button"
        aria-expanded={isOpen}
        onClick={() => toggleDateGroup(group.key)}
      >
        <span>{group.label}</span>
        <small>{group.fixtures.length} games</small>
        {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>
      {isOpen && (
        <div className="date-group-games">
          {group.fixtures.map((fixture) => (
            <button
              className={`fixture-button ${fixture.id === selectedId ? 'active' : ''}`}
              key={fixture.id}
              onClick={() => setSelectedId(fixture.id)}
            >
              <span>{fixture.home_team}</span>
              <strong>vs</strong>
              <span>{fixture.away_team}</span>
              <small>{gameTimeLabel(fixture.kickoff)} / {fixture.venue}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
})}
```

- [ ] **Step 7: Add accordion styles in `frontend/src/styles.css`**

Add below `.rail-head, .match-head`:

```css
.date-group {
  margin-top: 10px;
}

.date-group-toggle {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 8px;
  align-items: center;
  width: 100%;
  padding: 10px 12px;
  color: #1b1914;
  background: #fff0b8;
  border: 2px solid #1b1914;
  cursor: pointer;
  font-weight: 900;
  text-align: left;
}

.date-group-toggle span,
.date-group-toggle small {
  min-width: 0;
}

.date-group-toggle small {
  color: #5b5547;
  font-weight: 800;
  white-space: nowrap;
}

.date-group-games {
  padding-top: 10px;
}
```

- [ ] **Step 8: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 9: Run frontend tests**

Run:

```powershell
cd frontend
npm test
```

Expected: Vitest passes.

- [ ] **Step 10: Commit implementation**

Run:

```powershell
git add frontend/src/App.tsx frontend/src/styles.css frontend/src/fixtureGroups.ts frontend/src/__tests__/fixtureGroups.test.ts docs/superpowers/plans/2026-06-15-fixture-date-accordions.md
git commit -m "Add fixture date accordions"
```
