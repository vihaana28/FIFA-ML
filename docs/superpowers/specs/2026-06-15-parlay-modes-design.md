# Parlay Modes Design

## Goal

Replace the single global parlay recommendation with flexible parlay recommendations that support how the user wants to bet on a given day:

- one best option for each game
- one best option for each kickoff date
- selectable risk modes: simple, model, aggressive

The feature remains a strategy simulator. It must not place bets or imply guaranteed profit.

## Current Behavior

`app.recommendations.recommend_bets` returns:

- `best_singles`: top positive-EV moneyline bets across all fixtures
- `parlay_candidates`: one global parlay made from up to three top singles on different fixtures
- `avoid`: fixtures with no real odds or no edge

The frontend shows this as one "Parlay candidates" section. Odds ingestion currently stores h2h moneyline odds from The Odds API. Correct-score odds are supported only when already present in the odds payload. Spreads and totals are requested from the provider but not normalized into stored odds.

## Proposed Behavior

Return three parlay modes:

- `simple`: moneyline-only, lowest complexity, works with the current odds payload.
- `model`: same-game parlays from real market legs when odds exist, using model score-matrix joint probability.
- `aggressive`: same-game parlays that permit longer-shot combinations, still requiring real odds for every displayed leg.

Replace `parlay_candidates` with:

- `game_parlays`: one best parlay candidate per fixture per mode.
- `day_parlays`: one best parlay candidate per kickoff date per mode.

Keep `best_singles`, `avoid`, and the existing simulator warning.

## Backend Design

Add parlay-building helpers in `app.recommendations` or a small focused helper module. Inputs are fixture, prediction payload, stored odds payload, and mode.

For each fixture:

- Build moneyline leg candidates from h2h odds.
- Derive total-goals and both-teams-to-score probabilities from `adjusted_score_matrix`.
- Include totals and BTTS only when the odds payload contains real odds for those markets.
- Include exact-score legs only when `correct_scores` odds exist.
- For `simple`, choose the single best positive-EV moneyline leg and wrap it as that game's parlay output.
- For `model`, consider conservative compatible same-game combos such as moneyline plus under/over, or BTTS plus total, only when all legs have real odds.
- For `aggressive`, also consider exact-score and longer-shot combos that satisfy real-odds and positive-EV checks.

Same-game parlay probability must be computed from the score matrix by checking whether each scoreline satisfies all legs. Do not multiply same-game leg probabilities independently. Day parlays may multiply probabilities because they use different fixtures.

Day parlays:

- Group fixtures by kickoff calendar date.
- For each date and mode, select the best available game-level candidate from each fixture.
- Build up to three legs, ranked by expected value and edge.
- Return no candidate for a date/mode if fewer than two fixtures have usable positive-EV candidates.

Each parlay item should include:

- `mode`
- `fixture_id` or `date`
- `match` for game parlays
- `legs`
- `combined_probability`
- `decimal_odds`
- `expected_value_per_10`
- `risk_level`
- `reason`

Use stake `$10` for EV fields to match existing recommendation output.

## Frontend Design

Update recommendation types and helper summaries for `game_parlays` and `day_parlays`.

In the match panel, show "Best parlay for this game" using the selected mode. If no game parlay exists for that fixture/mode, show the backend reason.

In the recommendations section:

- Add a compact mode toggle: Simple, Model, Aggressive.
- Replace the old global "Parlay candidates" list with "Best parlay by day."
- Show date, probability, decimal odds, EV per $10, risk level, and leg labels.

Keep the existing manual Parlay Lab. It remains a user-built sandbox, separate from model recommendations.

## Testing

Backend TDD:

- `simple` mode returns one moneyline game parlay when only h2h odds exist.
- `day_parlays` groups fixtures by kickoff date and replaces the old global parlay behavior.
- Same-game combo probability is calculated from score-matrix outcomes, not by independent multiplication.
- Missing market odds produce a clear reason and no fake parlay leg.
- `/bets/recommendations` returns `game_parlays` and `day_parlays`.

Frontend TDD:

- Recommendation summary counts game and day parlays.
- Mode toggle filters displayed game/day parlay recommendations.
- Selected fixture shows that fixture's parlay candidate or fallback reason.

Verification:

```powershell
pytest
cd frontend
npm test
npm run build
```

## Assumptions

- Real odds are required for displayed betting legs.
- Simple mode should work before totals/BTTS odds ingestion is expanded.
- Model and aggressive modes may return fewer recommendations until additional markets are available.
- Same-game parlays are simulations; sportsbook-specific SGP pricing may differ from multiplying displayed leg odds.
