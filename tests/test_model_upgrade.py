from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.betting import expected_value
from app.calibration import calibrate_wdl
from app.db import Repository
from app.dixon_coles import apply_dixon_coles
from app.elo import aggregate_elo_profiles
from app.main import create_app
from app.model import TeamFeatures, expected_goals, score_matrix
from app.player_availability import aggregate_player_availability


def test_dixon_coles_preserves_probability_and_adjusts_low_scores():
    raw = score_matrix(1.25, 1.05)
    adjusted = apply_dixon_coles(raw, home_goals=1.25, away_goals=1.05, rho=-0.08)

    assert sum(cell["probability"] for cell in adjusted) == pytest.approx(1.0)
    raw_lookup = {cell["score"]: cell["probability"] for cell in raw}
    adjusted_lookup = {cell["score"]: cell["probability"] for cell in adjusted}
    assert adjusted_lookup["0-0"] != pytest.approx(raw_lookup["0-0"])
    assert adjusted_lookup["1-1"] != pytest.approx(raw_lookup["1-1"])


def test_elo_ingestion_maps_fixture_teams_to_profiles():
    repository = Repository(":memory:")
    rows = [
        {"rank": "1", "team": "Canada", "rating": "1775"},
        {"rank": "2", "team": "Bosnia-Herzegovina", "rating": "1620"},
    ]

    profiles = aggregate_elo_profiles(rows, repository.list_fixtures())

    canada = next(item for item in profiles["team_profiles"] if item["team_name"] == "Canada")
    assert canada["team_id"] == "canada"
    assert canada["elo"] == 1775
    assert canada["source"] == "World Football Elo"


def test_player_availability_lowers_strength_for_missing_important_player():
    rows = [
        {
            "team": "Canada",
            "player": "Key Striker",
            "status": "injured",
            "importance": "0.9",
            "minutes_share": "0.8",
            "attack_contribution": "0.7",
            "defense_contribution": "0.1",
        },
        {
            "team": "Canada",
            "player": "Starter",
            "status": "available",
            "importance": "0.5",
            "minutes_share": "0.6",
            "attack_contribution": "0.2",
            "defense_contribution": "0.2",
        },
    ]

    profiles = aggregate_player_availability(rows)
    canada = profiles["team_profiles"][0]

    assert canada["source"] == "Player Availability"
    assert canada["availability"] < 1
    assert canada["attack_availability"] < canada["defense_availability"]
    assert profiles["player_profiles"][0]["status"] == "injured"


def test_calibration_moves_low_confidence_model_toward_market():
    model = {"home": 0.65, "draw": 0.20, "away": 0.15}
    market = {"home": 0.45, "draw": 0.28, "away": 0.27}

    low = calibrate_wdl(model, market, confidence="low")
    high = calibrate_wdl(model, market, confidence="high")

    assert abs(low["home"] - market["home"]) < abs(high["home"] - market["home"])
    assert sum(low.values()) == pytest.approx(1.0)


def test_prediction_api_exposes_v2_fields_and_model_flags():
    client = TestClient(create_app(database_url=":memory:"))
    fixture = client.get("/fixtures").json()[0]

    prediction = client.get(f"/predictions/{fixture['id']}").json()

    assert prediction["model_version"] == "learned-poisson-dixon-coles-v1"
    assert prediction["model_type"] == "learned-poisson-dixon-coles-v1"
    assert prediction["raw_score_matrix"]
    assert prediction["adjusted_score_matrix"]
    assert prediction["calibrated_wdl"]
    assert set(prediction["data_quality"]) >= {"level", "score", "missing"}
    assert isinstance(prediction["risk_flags"], list)


def test_correct_score_endpoint_returns_ev_only_when_real_odds_exist():
    client = TestClient(create_app(database_url=":memory:"))
    fixture = client.get("/fixtures").json()[0]
    repository = client.app.state.repository
    repository.save_odds(
        fixture["id"],
        {
            "home": 100,
            "draw": 220,
            "away": 260,
            "correct_scores": {"1-0": 600, "1-1": 550},
            "source": "test-book",
        },
    )

    payload = client.get(f"/bets/correct-score/{fixture['id']}").json()

    assert payload["fixture_id"] == fixture["id"]
    assert payload["scores"]
    assert all("expected_value_per_10" in score for score in payload["scores"])


def test_parlay_risk_endpoint_blocks_same_match_correlated_legs():
    client = TestClient(create_app(database_url=":memory:"))
    fixture = client.get("/fixtures").json()[0]

    payload = client.get(
        "/bets/parlay-risk",
        params=[
            ("fixture_id", fixture["id"]),
            ("fixture_id", fixture["id"]),
        ],
    ).json()

    assert payload["correlated"] is True
    assert payload["risk_level"] == "high"


def test_admin_train_writes_backtest_metrics(tmp_path):
    model_path = tmp_path / "model.json"
    client = TestClient(create_app(database_url=":memory:", model_artifact_path=model_path))

    result = client.post("/admin/train").json()
    backtest = json.loads((tmp_path / "backtest.json").read_text(encoding="utf-8"))

    assert result["backtest"]["sample_matches"] >= 0
    assert set(backtest) >= {"sample_matches", "brier_score", "log_loss", "ranked_probability_score", "calibration_buckets"}
