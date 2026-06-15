# Fixture Date Accordions Design

## Goal

Make the Games rail easier to scan by grouping fixtures by kickoff date. Each date should be a collapsed dropdown section so users can open only the day they want and pick a game from that date.

## Current Behavior

`frontend/src/App.tsx` renders every fixture in one flat list inside `.fixture-rail`. Each game button includes the kickoff date/time and venue, but long fixture lists require scrolling through all games.

## Proposed Behavior

- Group fixtures by kickoff calendar date derived from `fixture.kickoff`.
- Sort date groups by kickoff date and games within each group by kickoff time.
- Render each date as a button-like accordion header with:
  - formatted date label
  - number of games on that date
  - chevron open/closed icon
- Keep all groups collapsed by default, except the group containing the selected game.
- When a user clicks a date header, toggle that date open or closed.
- When a user selects a game, set `selectedId` exactly as today and make sure that game's date group is open.

## Architecture

This is a frontend-only change. No API, database, model artifact, or backend route changes are needed because `Fixture` already includes `kickoff`.

Add small date-group helpers in `frontend/src/App.tsx`:

- `dateGroupKey(kickoff: string)`: stable `YYYY-MM-DD` key from kickoff date.
- `dateGroupLabel(kickoff: string)`: user-facing date label.
- `gameTimeLabel(kickoff: string)`: time-only label for game buttons.

Use `useMemo` to build grouped fixtures from `fixtures`, preserving efficient re-renders.

Add `openDateGroups` state as a `Record<string, boolean>` keyed by date group. A `useEffect` opens the selected fixture's date after fixtures or `selectedId` changes.

## UI Details

The left rail keeps existing visual style. New CSS classes should style date headers as compact controls, not nested cards. Game buttons remain unchanged except their small metadata can show time plus venue because date is now in the group header.

On mobile, accordion sections remain full width inside the existing one-column layout.

## Error Handling

If a kickoff date is invalid, place the game under an `Unscheduled` group and keep the app rendering. Existing prediction loading and API error behavior stay unchanged.

## Testing

Run the frontend build:

```powershell
cd frontend
npm run build
```

If time allows, run frontend tests:

```powershell
cd frontend
npm test
```

Manual check:

- The Games rail shows date groups instead of one flat list.
- Groups start collapsed except the selected fixture's date.
- Opening a date reveals its games.
- Clicking a game loads the existing prediction panel.
