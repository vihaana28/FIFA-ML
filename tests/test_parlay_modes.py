import pytest

from app.parlay_modes import build_day_parlays, build_game_parlay, same_game_probability


def _matrix():
    return [
        {"score": "0-0", "home_goals": 0, "away_goals": 0, "probability": 0.20},
        {"score": "1-0", "home_goals": 1, "away_goals": 0, "probability": 0.30},
        {"score": "1-1", "home_goals": 1, "away_goals": 1, "probability": 0.25},
        {"score": "2-1", "home_goals": 2, "away_goals": 1, "probability": 0.25},
    ]


def _prediction():
    return {
        "wdl": {"home": 0.55, "draw": 0.25, "away": 0.20},
        "adjusted_score_matrix": _matrix(),
        "confidence": "high",
    }


def _fixture(fixture_id="game-1", kickoff="2026-06-12T19:00:00Z"):
    return {
        "id": fixture_id,
        "home_team": "Canada",
        "away_team": "Brazil",
        "kickoff": kickoff,
    }


def test_same_game_probability_uses_score_matrix_not_independent_leg_multiplication():
    legs = [
        {"market": "moneyline", "selection_key": "home"},
        {"market": "total_goals", "selection_key": "under_2_5"},
    ]

    assert same_game_probability(_matrix(), legs) == pytest.approx(0.30)


def test_simple_mode_returns_best_positive_ev_moneyline_as_game_parlay():
    result = build_game_parlay(
        _fixture(),
        _prediction(),
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
        _fixture(),
        _prediction(),
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


def test_day_parlays_group_positive_game_parlays_by_kickoff_date():
    fixtures = [
        _fixture("game-1", "2026-06-12T19:00:00Z"),
        _fixture("game-2", "2026-06-12T22:00:00Z"),
        _fixture("game-3", "2026-06-13T19:00:00Z"),
    ]
    game_parlays = [
        build_game_parlay(fixture, _prediction(), {"home": 150, "draw": 260, "away": -130}, mode="simple", min_edge=0.01)
        for fixture in fixtures
    ]

    day_parlays = build_day_parlays(fixtures, game_parlays)

    assert len(day_parlays) == 1
    assert day_parlays[0]["date"] == "2026-06-12"
    assert day_parlays[0]["mode"] == "simple"
    assert len(day_parlays[0]["legs"]) == 2
