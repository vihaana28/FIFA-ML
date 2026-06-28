# Parlay Leg Detail Display Design

## Goal

Show the exact pick details inside every displayed parlay instead of only showing the match and generic reason.

## Current Behavior

`day_parlays` and `game_parlays` already include nested `legs` with selection, market, American odds, model probability, market probability, edge, and EV. The React UI currently renders parlay legs through a generic label helper, which collapses day-parlay legs to text like `England vs Croatia / Positive EV moneyline pick.`

## Design

Add a pure frontend helper that formats any recommendation leg into a readable betting line:

`England vs Croatia - England moneyline, +120, 56.3% model, 48.1% market, +8.2% edge, $2.05 EV/$10`

Use that helper in selected-game parlays and day-parlay cards. For nested day parlays, flatten nested game-parlay legs so each actual pick is visible. Keep the existing card summary for total probability, decimal odds, risk level, and EV.

## Testing

Add focused Vitest coverage for formatting a single moneyline leg and flattening nested day-parlay legs.
