from __future__ import annotations

from datetime import datetime
from itertools import combinations

from app.betting import american_to_decimal, expected_value, implied_probability, remove_vig


PARLAY_MODES = ("simple", "model", "aggressive")


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

    home_score = int(home)
    away_score = int(away)
    if leg["market"] == "moneyline":
        return (
            home_score > away_score
            and leg["selection_key"] == "home"
            or home_score == away_score
            and leg["selection_key"] == "draw"
            or home_score < away_score
            and leg["selection_key"] == "away"
        )
    if leg["market"] == "total_goals":
        total = home_score + away_score
        return total > 2.5 if leg["selection_key"] == "over_2_5" else total < 2.5
    if leg["market"] == "btts":
        both_score = home_score > 0 and away_score > 0
        return both_score if leg["selection_key"] == "yes" else not both_score
    if leg["market"] == "correct_score":
        return str(cell.get("score")) == leg["selection_key"]
    return False


def same_game_probability(score_matrix: list[dict], legs: list[dict]) -> float:
    return sum(float(cell["probability"]) for cell in score_matrix if all(_score_satisfies(cell, leg) for leg in legs))


def _leg(
    fixture: dict,
    market: str,
    selection_key: str,
    label: str,
    probability: float,
    american_odds: int | float,
    market_probability: float | None = None,
) -> dict:
    comparison_probability = market_probability if market_probability is not None else implied_probability(american_odds)
    return {
        "fixture_id": fixture["id"],
        "match": _match_label(fixture),
        "market": market,
        "selection_key": selection_key,
        "selection": label,
        "model_probability": probability,
        "market_probability": comparison_probability,
        "edge": probability - comparison_probability,
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


def _score_matrix(prediction: dict) -> list[dict]:
    return prediction.get("adjusted_score_matrix") or prediction.get("score_matrix") or []


def _market_legs(fixture: dict, prediction: dict, odds_payload: dict) -> list[dict]:
    score_matrix = _score_matrix(prediction)
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
    score_matrix = _score_matrix(prediction)
    odds = odds_payload.get("correct_scores") if isinstance(odds_payload.get("correct_scores"), dict) else {}
    legs = []
    for score, american_odds in odds.items():
        if not isinstance(american_odds, (int, float)):
            continue
        template = {"market": "correct_score", "selection_key": str(score)}
        probability = same_game_probability(score_matrix, [template])
        legs.append(_leg(fixture, "correct_score", str(score), f"Correct score {score}", probability, american_odds))
    return legs


def _combo_candidate(fixture: dict, legs: list[dict], score_matrix: list[dict], source: str, mode: str) -> dict:
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
        "risk_level": "high" if mode == "aggressive" or len(legs) > 2 else "medium",
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


def _positive_legs(legs: list[dict], min_edge: float) -> list[dict]:
    return [leg for leg in legs if leg["edge"] >= min_edge and leg["expected_value_per_10"] > 0]


def build_game_parlay(fixture: dict, prediction: dict, odds_payload: dict, mode: str, min_edge: float = 0.03) -> dict:
    if mode not in PARLAY_MODES:
        raise ValueError(f"Unknown parlay mode: {mode}")

    source = odds_payload.get("source", "unknown")
    moneyline = _positive_legs(_moneyline_legs(fixture, prediction, odds_payload), min_edge)
    if mode == "simple":
        if not moneyline:
            return _empty_game(fixture, mode, "No positive-EV moneyline leg.")
        return _single_candidate(fixture, max(moneyline, key=lambda leg: leg["expected_value_per_10"]), source, mode)

    candidate_legs = moneyline + _positive_legs(_market_legs(fixture, prediction, odds_payload), min_edge)
    if mode == "aggressive":
        candidate_legs.extend([leg for leg in _correct_score_legs(fixture, prediction, odds_payload) if leg["expected_value_per_10"] > 0])

    score_matrix = _score_matrix(prediction)
    combos = []
    max_legs = 3 if mode == "aggressive" else 2
    for size in range(2, max_legs + 1):
        for combo in combinations(candidate_legs, size):
            if len({leg["market"] for leg in combo}) != len(combo):
                continue
            scored = _combo_candidate(fixture, list(combo), score_matrix, source, mode)
            if scored["combined_probability"] > 0 and scored["expected_value_per_10"] > 0:
                combos.append(scored)

    if combos:
        return max(combos, key=lambda item: item["expected_value_per_10"])
    if moneyline:
        return _single_candidate(fixture, max(moneyline, key=lambda leg: leg["expected_value_per_10"]), source, mode)
    return _empty_game(fixture, mode, "No real positive-EV legs for this mode.")


def build_day_parlays(fixtures: list[dict], game_parlays: list[dict]) -> list[dict]:
    by_fixture = {(item["fixture_id"], item["mode"]): item for item in game_parlays if item.get("legs")}
    grouped: dict[tuple[str, str], list[dict]] = {}
    for fixture in fixtures:
        day = _kickoff_date(fixture.get("kickoff", ""))
        for mode in PARLAY_MODES:
            candidate = by_fixture.get((fixture["id"], mode))
            if candidate:
                grouped.setdefault((day, mode), []).append(candidate)

    results = []
    for (day, mode), candidates in sorted(grouped.items()):
        selected = sorted(candidates, key=lambda item: item["expected_value_per_10"], reverse=True)[:3]
        if len(selected) < 2:
            continue
        combined_probability = 1.0
        decimal_odds = 1.0
        for candidate in selected:
            combined_probability *= candidate["combined_probability"]
            decimal_odds *= candidate["decimal_odds"]
        profit = 10 * decimal_odds - 10
        results.append(
            {
                "mode": mode,
                "date": day,
                "legs": selected,
                "combined_probability": combined_probability,
                "decimal_odds": decimal_odds,
                "expected_value_per_10": (combined_probability * profit) - ((1 - combined_probability) * 10),
                "risk_level": "high" if mode == "aggressive" or len(selected) >= 3 else "medium",
                "reason": "Positive EV day parlay.",
            }
        )
    return results
