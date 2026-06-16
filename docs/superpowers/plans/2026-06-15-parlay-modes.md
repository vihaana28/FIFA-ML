# Parlay Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single global parlay recommendation with simple, model, and aggressive per-game and per-day parlay recommendations.

**Architecture:** Add pure parlay construction in `app/parlay_modes.py` so score-matrix probability logic is testable without FastAPI. `app.recommendations` will call those helpers while keeping existing `best_singles` and `avoid` behavior. The React app will add a compact mode toggle and render selected-game and by-day parlays from the new API shape.

**Tech Stack:** Python 3.11, FastAPI, pytest, React 19, TypeScript, Vite, Vitest.

---

## File Structure

- Create `app/parlay_modes.py`: parlay modes, leg construction, same-game joint probability from score matrix, and day grouping.
- Modify `app/recommendations.py`: replace `_build_parlay_candidates` with `game_parlays` and `day_parlays`.
- Modify `tests/test_sync_and_recommendations.py`: backend API contract and simple/day behavior tests.
- Create `tests/test_parlay_modes.py`: focused same-game probability tests.
- Modify `frontend/src/api.ts`: new recommendation and parlay types.
- Modify `frontend/src/betting.ts`: recommendation summary and mode selection helpers.
- Modify `frontend/src/__tests__/betting.test.ts`: frontend helper tests.
- Modify `frontend/src/App.tsx`: mode toggle, selected-game parlay panel, and by-day parlay list.
- Modify `frontend/src/styles.css`: compact mode toggle and parlay card styles.

---

### Task 1: Backend Pure Parlay Mode Helpers

**Files:**
- Create: `app/parlay_modes.py`
- Create: `tests/test_parlay_modes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_parlay_modes.py`:

```python
import pytest

from app.parlay_modes import build_game_parlay, same_game_probability


def matrix():
    return [
        {"score": "0-0", "home_goals": 0, "away_goals": 0, "probability": 0.20},
        {"score": "1-0", "home_goals": 1, "away_goals": 0, "probability": 0.30},
        {"score": "1-1", "home_goals": 1, "away_goals": 1, "probability": 0.25},
        {"score": "2-1", "home_goals": 2, "away_goals": 1, "probability": 0.25},
    ]


def prediction():
    return {
        "wdl": {"home": 0.55, "draw": 0.25, "away": 0.20},
        "adjusted_score_matrix": matrix(),
        "confidence": "high",
    }


def fixture():
    return {
        "id": "game-1",
        "home_team": "Canada",
        "away_team": "Brazil",
        "kickoff": "2026-06-12T19:00:00Z",
    }


def test_same_game_probability_uses_score_matrix_not_independent_leg_multiplication():
    legs = [
        {"market": "moneyline", "selection_key": "home"},
        {"market": "total_goals", "selection_key": "under_2_5"},
    ]

    assert same_game_probability(matrix(), legs) == pytest.approx(0.30)


def test_simple_mode_returns_best_positive_ev_moneyline_as_game_parlay():
    result = build_game_parlay(
        fixture(),
        prediction(),
        {"home": 150, "draw": 260, "away": -130, "source": "test-book"},
        mode="simple",
        min_edge=0.01,
    )

    assert result["mode"] == "simple"
    assert result["fixture_id"] == "game-1"
    assert result["legs"][0]["market"] == "moneyline"
    assert result["legs"][0]["selection_key"] == "home"
    assert result["combined_probability"] == pytest.approx(0.55)
    assert result["expected_value_per_10"] > 0


def test_model_mode_uses_real_totals_odds_for_same_game_combo():
    result = build_game_parlay(
        fixture(),
        prediction(),
        {
            "home": 150,
            "draw": 260,
            "away": -130,
            "totals": {"over_2_5": 120, "under_2_5": 140},
            "source": "test-book",
        },
        mode="model",
        min_edge=0.01,
    )

    assert result["mode"] == "model"
    assert len(result["legs"]) >= 1
    assert all("american_odds" in leg for leg in result["legs"])
    assert result["reason"] == "Positive EV model parlay."
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
pytest tests/test_parlay_modes.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.parlay_modes'`.

- [ ] **Step 3: Implement `app/parlay_modes.py`**

Create `app/parlay_modes.py`:

```python
from __future__ import annotations

from datetime import datetime
from itertools import combinations
from typing import Callable

from app.betting import american_to_decimal, expected_value, implied_probability, parlay_outcome, remove_vig


PARLAY_MODES = ("simple", "model", "aggressive")
MONEYLINE_LABELS = {"home": "Home", "draw": "Draw", "away": "Away"}


def _match_label(fixture: dict) -> str:
    return f"{fixture['home_team']} vs {fixture['away_team']}"


def _kickoff_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return "unscheduled"


def _score_satisfies(cell: dict, leg: dict) -> bool:
    home = cell.get("home_goals")
    away = cell.get("away_goals")
    if home is None or away is None:
        return False
    if leg["market"] == "moneyline":
        return (home > away and leg["selection_key"] == "home") or (home == away and leg["selection_key"] == "draw") or (
            home < away and leg["selection_key"] == "away"
        )
    if leg["market"] == "total_goals":
        total = int(home) + int(away)
        return total > 2.5 if leg["selection_key"] == "over_2_5" else total < 2.5
    if leg["market"] == "btts":
        yes = int(home) > 0 and int(away) > 0
        return yes if leg["selection_key"] == "yes" else not yes
    if leg["market"] == "correct_score":
        return str(cell.get("score")) == leg["selection_key"]
    return False


def same_game_probability(score_matrix: list[dict], legs: list[dict]) -> float:
    return sum(float(cell["probability"]) for cell in score_matrix if all(_score_satisfies(cell, leg) for leg in legs))


def _probability_from_matrix(score_matrix: list[dict], leg: dict, fallback: float) -> float:
    if leg["market"] == "moneyline":
        return fallback
    return same_game_probability(score_matrix, [leg])


def _leg(
    fixture: dict,
    market: str,
    selection_key: str,
    label: str,
    probability: float,
    american_odds: int | float,
    market_probability: float | None = None,
) -> dict:
    implied = implied_probability(american_odds)
    return {
        "fixture_id": fixture["id"],
        "match": _match_label(fixture),
        "market": market,
        "selection_key": selection_key,
        "selection": label,
        "model_probability": probability,
        "market_probability": market_probability if market_probability is not None else implied,
        "edge": probability - (market_probability if market_probability is not None else implied),
        "american_odds": int(american_odds),
        "expected_value_per_10": expected_value(probability, american_odds, stake=10),
    }


def _moneyline_legs(fixture: dict, prediction: dict, odds_payload: dict) -> list[dict]:
    market = {key: odds_payload[key] for key in ("home", "draw", "away") if isinstance(odds_payload.get(key), (int, float))}
    if set(market) != {"home", "draw", "away"}:
        return []
    fair_market = remove_vig(market)
    labels = {"home": fixture["home_team"], "draw": "Draw", "away": fixture["away_team"]}
    return [
        _leg(fixture, "moneyline", key, labels[key], float(prediction["wdl"][key]), market[key], fair_market[key])
        for key in ("home", "draw", "away")
    ]


def _market_legs(fixture: dict, prediction: dict, odds_payload: dict) -> list[dict]:
    score_matrix = prediction.get("adjusted_score_matrix") or prediction.get("score_matrix") or []
    legs = []
    totals = odds_payload.get("totals") if isinstance(odds_payload.get("totals"), dict) else {}
    for key, label in {"over_2_5": "Over 2.5 goals", "under_2_5": "Under 2.5 goals"}.items():
        if isinstance(totals.get(key), (int, float)):
            template = {"market": "total_goals", "selection_key": key}
            legs.append(_leg(fixture, "total_goals", key, label, same_game_probability(score_matrix, [template]), totals[key]))
    btts = odds_payload.get("btts") if isinstance(odds_payload.get("btts"), dict) else {}
    for key, label in {"yes": "Both teams score", "no": "Both teams do not score"}.items():
        if isinstance(btts.get(key), (int, float)):
            template = {"market": "btts", "selection_key": key}
            legs.append(_leg(fixture, "btts", key, label, same_game_probability(score_matrix, [template]), btts[key]))
    return legs


def _correct_score_legs(fixture: dict, prediction: dict, odds_payload: dict) -> list[dict]:
    score_matrix = prediction.get("adjusted_score_matrix") or prediction.get("score_matrix") or []
    odds = odds_payload.get("correct_scores") if isinstance(odds_payload.get("correct_scores"), dict) else {}
    legs = []
    for score, american_odds in odds.items():
        if not isinstance(american_odds, (int, float)):
            continue
        template = {"market": "correct_score", "selection_key": str(score)}
        legs.append(_leg(fixture, "correct_score", str(score), f"Correct score {score}", same_game_probability(score_matrix, [template]), american_odds))
    return legs


def _score_combo(score_matrix: list[dict], legs: list[dict], source: str, mode: str, fixture: dict) -> dict:
    probability = same_game_probability(score_matrix, legs)
    decimal_odds = 1.0
    for leg in legs:
        decimal_odds *= american_to_decimal(leg["american_odds"])
    profit = 10 * decimal_odds - 10
    return {
        "mode": mode,
        "fixture_id": fixture["id"],
        "match": _match_label(fixture),
        "legs": legs,
        "combined_probability": probability,
        "decimal_odds": decimal_odds,
        "expected_value_per_10": (probability * profit) - ((1 - probability) * 10),
        "risk_level": "high" if mode == "aggressive" or len(legs) > 2 else "medium" if len(legs) > 1 else "low",
        "reason": "Positive EV model parlay.",
        "source": source,
    }


def _single_candidate(fixture: dict, leg: dict, source: str, mode: str) -> dict:
    return {
        "mode": mode,
        "fixture_id": fixture["id"],
        "match": _match_label(fixture),
        "legs": [leg],
        "combined_probability": leg["model_probability"],
        "decimal_odds": american_to_decimal(leg["american_odds"]),
        "expected_value_per_10": leg["expected_value_per_10"],
        "risk_level": "low",
        "reason": "Positive EV moneyline pick." if mode == "simple" else "Positive EV model parlay.",
        "source": source,
    }


def build_game_parlay(fixture: dict, prediction: dict, odds_payload: dict, mode: str, min_edge: float = 0.03) -> dict:
    source = odds_payload.get("source", "unknown")
    moneyline = _moneyline_legs(fixture, prediction, odds_payload)
    positive_moneyline = [leg for leg in moneyline if leg["edge"] >= min_edge and leg["expected_value_per_10"] > 0]
    if mode == "simple":
        if not positive_moneyline:
            return _empty_game(fixture, mode, "No positive-EV moneyline leg.")
        return _single_candidate(fixture, max(positive_moneyline, key=lambda leg: leg["expected_value_per_10"]), source, mode)

    score_matrix = prediction.get("adjusted_score_matrix") or prediction.get("score_matrix") or []
    legs = positive_moneyline + [leg for leg in _market_legs(fixture, prediction, odds_payload) if leg["edge"] >= min_edge and leg["expected_value_per_10"] > 0]
    if mode == "aggressive":
        legs.extend([leg for leg in _correct_score_legs(fixture, prediction, odds_payload) if leg["expected_value_per_10"] > 0])
    combos = []
    max_legs = 3 if mode == "aggressive" else 2
    for size in range(2, max_legs + 1):
        for combo in combinations(legs, size):
            markets = {leg["market"] for leg in combo}
            if len(markets) != len(combo):
                continue
            scored = _score_combo(score_matrix, list(combo), source, mode, fixture)
            if scored["expected_value_per_10"] > 0 and scored["combined_probability"] > 0:
                combos.append(scored)
    if combos:
        return max(combos, key=lambda item: item["expected_value_per_10"])
    if positive_moneyline:
        return _single_candidate(fixture, max(positive_moneyline, key=lambda leg: leg["expected_value_per_10"]), source, mode)
    return _empty_game(fixture, mode, "No real positive-EV legs for this mode.")


def _empty_game(fixture: dict, mode: str, reason: str) -> dict:
    return {
        "mode": mode,
        "fixture_id": fixture["id"],
        "match": _match_label(fixture),
        "legs": [],
        "combined_probability": 0.0,
        "decimal_odds": 0.0,
        "expected_value_per_10": 0.0,
        "risk_level": "none",
        "reason": reason,
        "source": "unknown",
    }


def build_day_parlays(fixtures: list[dict], game_parlays: list[dict]) -> list[dict]:
    by_fixture = {(item["fixture_id"], item["mode"]): item for item in game_parlays if item.get("legs")}
    day_modes: dict[tuple[str, str], list[dict]] = {}
    for fixture in fixtures:
        day = _kickoff_date(fixture.get("kickoff", ""))
        for mode in PARLAY_MODES:
            candidate = by_fixture.get((fixture["id"], mode))
            if candidate:
                day_modes.setdefault((day, mode), []).append(candidate)
    results = []
    for (day, mode), candidates in sorted(day_modes.items()):
        selected = sorted(candidates, key=lambda item: item["expected_value_per_10"], reverse=True)[:3]
        if len(selected) < 2:
            continue
        outcome = parlay_outcome(
            [{"probability": item["combined_probability"], "american_odds": _decimal_to_representative_american(item["decimal_odds"])} for item in selected],
            stake=10,
        )
        results.append(
            {
                "mode": mode,
                "date": day,
                "legs": selected,
                "combined_probability": outcome["combined_probability"],
                "decimal_odds": outcome["decimal_odds"],
                "expected_value_per_10": outcome["expected_value"],
                "risk_level": "high" if mode == "aggressive" or len(selected) >= 3 else "medium",
                "reason": "Positive EV day parlay.",
            }
        )
    return results


def _decimal_to_representative_american(decimal_value: float) -> int:
    if decimal_value >= 2:
        return round((decimal_value - 1) * 100)
    return round(-100 / (decimal_value - 1))
```

- [ ] **Step 4: Run backend helper tests**

Run:

```powershell
pytest tests/test_parlay_modes.py -q
```

Expected: PASS.

---

### Task 2: Recommendation API Contract

**Files:**
- Modify: `app/recommendations.py`
- Modify: `tests/test_sync_and_recommendations.py`

- [ ] **Step 1: Write failing recommendation contract tests**

Append to `tests/test_sync_and_recommendations.py`:

```python
def test_recommendations_return_game_and_day_parlays_instead_of_global_parlay():
    repository = Repository(":memory:")
    fixtures = repository.list_fixtures()[:2]
    for fixture in fixtures:
        repository.save_odds(
            fixture["id"],
            {"home": 180, "draw": 260, "away": -120, "source": "test-book", "last_updated": "2026-06-12T12:00:00Z"},
        )

    result = recommend_bets(repository, min_edge=0.01)

    assert "parlay_candidates" not in result
    assert result["game_parlays"]
    assert result["day_parlays"]
    assert {item["mode"] for item in result["game_parlays"]} >= {"simple", "model", "aggressive"}
    assert {item["mode"] for item in result["day_parlays"]} >= {"simple"}
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
pytest tests/test_sync_and_recommendations.py::test_recommendations_return_game_and_day_parlays_instead_of_global_parlay -q
```

Expected: FAIL because `parlay_candidates` still exists and `game_parlays`/`day_parlays` do not.

- [ ] **Step 3: Update `app/recommendations.py`**

Import helpers:

```python
from app.parlay_modes import PARLAY_MODES, build_day_parlays, build_game_parlay
```

Inside `recommend_bets`, initialize:

```python
    game_parlays: list[dict] = []
```

After each valid prediction/market block, append mode candidates:

```python
        for mode in PARLAY_MODES:
            game_parlays.append(build_game_parlay(fixture, prediction, odds_payload, mode=mode, min_edge=min_edge))
```

Replace final parlay block:

```python
    parlay_candidates = _build_parlay_candidates(best_singles)
    result = {
        "best_singles": best_singles[:12],
        "parlay_candidates": parlay_candidates,
        "avoid": avoid[:12],
        "warning": "...",
    }
```

With:

```python
    result = {
        "best_singles": best_singles[:12],
        "game_parlays": game_parlays,
        "day_parlays": build_day_parlays(repository.list_fixtures(), game_parlays),
        "avoid": avoid[:12],
        "warning": "Strategy simulator only. No guarantee, no sportsbook execution, and parlays assume independent legs only across different fixtures.",
    }
```

Delete `_build_parlay_candidates` if no longer referenced.

- [ ] **Step 4: Run recommendation tests**

Run:

```powershell
pytest tests/test_sync_and_recommendations.py -q
```

Expected: PASS after updating older endpoint section assertion from `parlay_candidates` to `game_parlays` and `day_parlays`.

---

### Task 3: Frontend Types and Helpers

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/betting.ts`
- Modify: `frontend/src/__tests__/betting.test.ts`

- [ ] **Step 1: Write failing frontend helper test**

Update the recommendation summary test in `frontend/src/__tests__/betting.test.ts` to use:

```ts
const summary = recommendationSummary({
  best_singles: [{ edge: 0.052, expected_value_per_10: 1.44 }],
  game_parlays: [{ mode: 'simple', fixture_id: 'game-1', match: 'A vs B', legs: [], combined_probability: 0.54, decimal_odds: 2.1, expected_value_per_10: 1.2, risk_level: 'low', reason: 'Positive EV moneyline pick.' }],
  day_parlays: [{ mode: 'simple', date: '2026-06-12', legs: [], combined_probability: 0.31, decimal_odds: 4.2, expected_value_per_10: 2.1, risk_level: 'medium', reason: 'Positive EV day parlay.' }],
  avoid: [{ reason: 'No real moneyline odds available.' }, { reason: 'No positive EV edge above threshold.' }],
  warning: 'Strategy simulator only.',
})

expect(summary.bestEdge).toBe('5.2%')
expect(summary.singleCount).toBe(1)
expect(summary.gameParlayCount).toBe(1)
expect(summary.dayParlayCount).toBe(1)
expect(summary.avoidCount).toBe(2)
```

- [ ] **Step 2: Run frontend helper test to verify failure**

Run:

```powershell
cd frontend
npm test -- betting
```

Expected: FAIL because `RecommendationPayload` and summary still expect `parlay_candidates`.

- [ ] **Step 3: Update TypeScript types**

In `frontend/src/api.ts`, define:

```ts
export type ParlayMode = 'simple' | 'model' | 'aggressive'

export type RecommendedParlay = {
  mode: ParlayMode
  fixture_id?: string
  date?: string
  match?: string
  legs: Array<BetRecommendation | RecommendedParlay>
  combined_probability: number
  decimal_odds: number
  expected_value_per_10: number
  risk_level: 'none' | 'low' | 'medium' | 'high'
  reason: string
  source?: string
}
```

Replace `ParlayCandidate` and `Recommendations` with:

```ts
export type Recommendations = {
  best_singles: BetRecommendation[]
  game_parlays: RecommendedParlay[]
  day_parlays: RecommendedParlay[]
  avoid: Array<{ fixture_id: string; match: string; reason: string }>
  warning: string
}
```

- [ ] **Step 4: Update `frontend/src/betting.ts` helper types**

Change `RecommendationPayload` to:

```ts
type RecommendationPayload = {
  best_singles: Array<{ edge: number; expected_value_per_10: number }>
  game_parlays: Array<{ combined_probability: number }>
  day_parlays: Array<{ combined_probability: number }>
  avoid: Array<{ reason: string }>
  warning: string
}
```

Return:

```ts
return {
  singleCount: recommendations.best_singles.length,
  gameParlayCount: recommendations.game_parlays.length,
  dayParlayCount: recommendations.day_parlays.length,
  avoidCount: recommendations.avoid.length,
  bestEdge: best ? formatPercent(best.edge) : '0.0%',
}
```

- [ ] **Step 5: Run frontend helper tests**

Run:

```powershell
cd frontend
npm test -- betting
```

Expected: PASS.

---

### Task 4: Frontend Rendering

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Update imports and state**

Import `type ParlayMode` from `./api` and add:

```ts
const [parlayMode, setParlayMode] = useState<ParlayMode>('simple')
```

Add derived values:

```ts
const selectedGameParlay = recommendations?.game_parlays.find(
  (item) => item.fixture_id === selectedId && item.mode === parlayMode,
)
const dayParlays = recommendations?.day_parlays.filter((item) => item.mode === parlayMode) ?? []
```

- [ ] **Step 2: Add mode toggle JSX**

In the recommendations header, render:

```tsx
<div className="mode-toggle" role="group" aria-label="Parlay mode">
  {(['simple', 'model', 'aggressive'] as const).map((mode) => (
    <button
      className={parlayMode === mode ? 'active' : ''}
      key={mode}
      type="button"
      onClick={() => setParlayMode(mode)}
    >
      {mode}
    </button>
  ))}
</div>
```

- [ ] **Step 3: Add selected game parlay panel**

After the market edge block in selected match content, render:

```tsx
<section className="panel-block selected-parlay">
  <h3><Target size={17} /> Best parlay for this game</h3>
  {selectedGameParlay && selectedGameParlay.legs.length > 0 ? (
    <div className={`parlay-card ${selectedGameParlay.risk_level}`}>
      <strong>{formatPercent(selectedGameParlay.combined_probability)} probability</strong>
      <span>{selectedGameParlay.decimal_odds.toFixed(2)} decimal odds</span>
      <span>${selectedGameParlay.expected_value_per_10.toFixed(2)} EV per $10</span>
      <small>{selectedGameParlay.risk_level} risk / {selectedGameParlay.reason}</small>
      {selectedGameParlay.legs.map((leg, index) => (
        <small key={`${selectedGameParlay.fixture_id}-${index}`}>
          {'selection' in leg ? leg.selection : leg.match}
        </small>
      ))}
    </div>
  ) : (
    <p className="muted">{selectedGameParlay?.reason ?? 'No parlay available for this game and mode.'}</p>
  )}
</section>
```

- [ ] **Step 4: Replace old parlay candidate list**

Replace `recommendations.parlay_candidates` rendering with `dayParlays` rendering:

```tsx
<h3>Best parlay by day</h3>
{dayParlays.length === 0 ? (
  <p className="muted">Need 2+ usable games on a day for this mode.</p>
) : (
  dayParlays.map((candidate) => (
    <div className={`parlay-card ${candidate.risk_level}`} key={`${candidate.mode}-${candidate.date}`}>
      <strong>{candidate.date} / {formatPercent(candidate.combined_probability)} probability</strong>
      <span>{candidate.decimal_odds.toFixed(2)} decimal odds</span>
      <span>${candidate.expected_value_per_10.toFixed(2)} EV per $10</span>
      <small>{candidate.risk_level} risk / {candidate.reason}</small>
      {candidate.legs.map((leg, index) => (
        <small key={`${candidate.date}-${index}`}>
          {leg.match ?? 'Game parlay'} / {leg.reason}
        </small>
      ))}
    </div>
  ))
)}
```

- [ ] **Step 5: Add CSS**

Add to `frontend/src/styles.css`:

```css
.mode-toggle {
  display: inline-grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
  border: 2px solid #1b1914;
  background: #1b1914;
}

.mode-toggle button {
  min-height: 36px;
  padding: 0 12px;
  border: 0;
  background: #fff8dc;
  color: #1b1914;
  cursor: pointer;
  font-weight: 900;
  text-transform: capitalize;
}

.mode-toggle button.active {
  background: #4f8f6f;
  color: #fffaf0;
}

.selected-parlay {
  margin-top: 16px;
}

.parlay-card.low {
  border-left: 5px solid #4f8f6f;
}

.parlay-card.medium {
  border-left: 5px solid #d99a2b;
}

.parlay-card.high {
  border-left: 5px solid #b4443f;
}
```

- [ ] **Step 6: Run frontend tests and build**

Run:

```powershell
cd frontend
npm test
npm run build
```

Expected: PASS.

---

### Task 5: Full Verification

**Files:**
- Verify all modified backend and frontend files.

- [ ] **Step 1: Run full backend suite**

Run:

```powershell
pytest
```

Expected: PASS.

- [ ] **Step 2: Run full frontend suite and build**

Run:

```powershell
cd frontend
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 3: Commit implementation**

Run:

```powershell
git add app/parlay_modes.py app/recommendations.py tests/test_parlay_modes.py tests/test_sync_and_recommendations.py frontend/src/api.ts frontend/src/betting.ts frontend/src/__tests__/betting.test.ts frontend/src/App.tsx frontend/src/styles.css docs/superpowers/plans/2026-06-15-parlay-modes.md
git commit -m "Add parlay mode recommendations"
```
