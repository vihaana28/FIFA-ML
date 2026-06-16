from __future__ import annotations

import pytest

from app.recent_form import aggregate_recent_form_profiles


def test_recent_form_weights_friendlies_less_than_competitive_matches():
    rows = [
        {
            "date": "2026-01-10",
            "home_team": "Canada",
            "away_team": "Mexico",
            "home_score": "2",
            "away_score": "0",
            "tournament": "Friendly",
        },
        {
            "date": "2026-02-10",
            "home_team": "Canada",
            "away_team": "Mexico",
            "home_score": "2",
            "away_score": "0",
            "tournament": "CONCACAF Nations League",
        },
    ]

    profiles = aggregate_recent_form_profiles(rows, reference_date="2026-06-13")
    canada = next(item for item in profiles["team_profiles"] if item["team_name"] == "Canada")

    assert canada["source"] == "International Results + Friendlies"
    assert canada["matches"] == 2
    assert canada["friendly_matches"] == 1
    assert canada["competitive_matches"] == 1
    assert canada["weighted_matches"] == pytest.approx(1.10)
    assert canada["weighted_goals"] == pytest.approx(2.20)
    assert canada["recent_form_score"] > 0.5


def test_current_world_cup_results_get_full_weight_over_old_friendlies():
    rows = [
        {
            "date": "2023-01-10",
            "home_team": "Qatar",
            "away_team": "Switzerland",
            "home_score": "4",
            "away_score": "0",
            "tournament": "Friendly",
        },
        {
            "date": "2026-06-13",
            "home_team": "Qatar",
            "away_team": "Switzerland",
            "home_score": "0",
            "away_score": "2",
            "tournament": "FIFA World Cup",
        },
    ]

    profiles = aggregate_recent_form_profiles(rows, reference_date="2026-06-13")
    qatar = next(item for item in profiles["team_profiles"] if item["team_name"] == "Qatar")

    assert qatar["weighted_goals_against"] > qatar["weighted_goals"]
    assert qatar["losses"] == 1
    assert qatar["friendly_matches"] == 1
