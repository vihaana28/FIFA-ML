from __future__ import annotations

from app.betting import expected_value, remove_vig
from app.db import Repository
from app.model import predict_match
from app.parlay_modes import PARLAY_MODES, build_day_parlays, build_game_parlay


MONEYLINE_KEYS = ("home", "draw", "away")


def moneyline_market(odds_payload: dict) -> dict[str, float | int]:
    return {key: odds_payload[key] for key in MONEYLINE_KEYS if isinstance(odds_payload.get(key), (int, float))}


def build_prediction(repository: Repository, fixture: dict) -> dict:
    home = repository.get_team_features(fixture["home_team_id"])
    away = repository.get_team_features(fixture["away_team_id"])
    return predict_match(fixture["id"], home, away)


def recommend_bets(repository: Repository, min_edge: float = 0.03, max_plus_odds: int = 650) -> dict:
    best_singles: list[dict] = []
    avoid: list[dict] = []
    game_parlays: list[dict] = []

    fixtures = repository.list_fixtures()
    for fixture in fixtures:
        odds_payload = repository.get_odds(fixture["id"])
        prediction = build_prediction(repository, fixture)
        for mode in PARLAY_MODES:
            game_parlays.append(build_game_parlay(fixture, prediction, odds_payload, mode=mode, min_edge=min_edge))

        market = moneyline_market(odds_payload)
        if set(market) != set(MONEYLINE_KEYS):
            avoid.append(
                {
                    "fixture_id": fixture["id"],
                    "match": f"{fixture['home_team']} vs {fixture['away_team']}",
                    "reason": "No real moneyline odds available.",
                }
            )
            continue

        fair_market = remove_vig(market)
        labels = {"home": fixture["home_team"], "draw": "Draw", "away": fixture["away_team"]}
        fixture_recommendations = []
        for outcome in MONEYLINE_KEYS:
            if market[outcome] > max_plus_odds:
                continue
            model_probability = prediction["wdl"][outcome]
            edge = model_probability - fair_market[outcome]
            ev = expected_value(model_probability, market[outcome], stake=10)
            if edge >= min_edge and ev > 0:
                fixture_recommendations.append(
                    {
                        "fixture_id": fixture["id"],
                        "match": f"{fixture['home_team']} vs {fixture['away_team']}",
                        "selection": labels[outcome],
                        "market": "moneyline",
                        "model_probability": model_probability,
                        "market_probability": fair_market[outcome],
                        "edge": edge,
                        "expected_value_per_10": ev,
                        "american_odds": market[outcome],
                        "confidence": prediction["confidence"],
                        "source": odds_payload.get("source", "unknown"),
                        "last_updated": odds_payload.get("last_updated"),
                    }
                )

        if fixture_recommendations:
            best_singles.extend(fixture_recommendations)
        else:
            avoid.append(
                {
                    "fixture_id": fixture["id"],
                    "match": f"{fixture['home_team']} vs {fixture['away_team']}",
                    "reason": "No positive EV edge above threshold.",
                }
            )

    best_singles.sort(key=lambda item: (item["expected_value_per_10"], item["edge"]), reverse=True)
    result = {
        "best_singles": best_singles[:12],
        "game_parlays": game_parlays,
        "day_parlays": build_day_parlays(fixtures, game_parlays),
        "avoid": avoid[:12],
        "warning": "Strategy simulator only. No guarantee, no sportsbook execution, and parlays assume independent legs only across different fixtures.",
    }
    repository.save_recommendations(result)
    return result
