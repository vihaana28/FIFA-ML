from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.db import Repository
from app.learned_model import (
    build_training_examples,
    load_learned_goal_model,
    parse_football_data_training_matches,
    parse_international_results_training_matches,
    parse_openfootball_training_matches,
    train_learned_goal_model,
)
from app.main import create_app
from app.model import TeamFeatures, predict_match


def test_international_results_adapter_normalizes_free_csv_rows():
    rows = [
        {
            "date": "2024-06-01",
            "home_team": "Canada",
            "away_team": "Mexico",
            "home_score": "2",
            "away_score": "1",
            "tournament": "CONCACAF Nations League",
            "neutral": "FALSE",
        },
        {"date": "bad", "home_team": "Skip", "away_team": "Bad", "home_score": "x", "away_score": "0"},
    ]

    matches = parse_international_results_training_matches(rows)

    assert len(matches) == 1
    assert matches[0].home_team == "Canada"
    assert matches[0].away_team == "Mexico"
    assert matches[0].home_score == 2
    assert matches[0].away_score == 1
    assert matches[0].source == "martj42/international_results"


def test_openfootball_training_adapter_uses_finished_world_cup_scores():
    payload = {
        "matches": [
            {
                "date": "2022-11-20",
                "team1": "Qatar",
                "team2": "Ecuador",
                "score1": 0,
                "score2": 2,
                "round": "Group Stage",
            },
            {"date": "2026-06-11", "team1": "Mexico", "team2": "South Africa"},
        ]
    }

    matches = parse_openfootball_training_matches(payload)

    assert len(matches) == 1
    assert matches[0].home_team == "Qatar"
    assert matches[0].away_team == "Ecuador"
    assert matches[0].source == "openfootball/worldcup"


def test_football_data_training_adapter_reads_finished_scores_only():
    payload = {
        "matches": [
            {
                "utcDate": "2026-06-13T00:00:00Z",
                "homeTeam": {"name": "USA"},
                "awayTeam": {"name": "Paraguay"},
                "status": "FINISHED",
                "score": {"fullTime": {"home": 3, "away": 1}},
                "competition": {"name": "FIFA World Cup"},
            },
            {
                "utcDate": "2026-06-14T00:00:00Z",
                "homeTeam": {"name": "Brazil"},
                "awayTeam": {"name": "Morocco"},
                "status": "TIMED",
                "score": {"fullTime": {"home": None, "away": None}},
            },
        ]
    }

    matches = parse_football_data_training_matches(payload)

    assert len(matches) == 1
    assert matches[0].home_team == "USA"
    assert matches[0].away_team == "Paraguay"
    assert matches[0].source == "football-data.org"


def test_training_examples_use_only_prior_matches_for_rolling_features():
    rows = [
        {
            "date": "2024-01-01",
            "home_team": "Canada",
            "away_team": "Mexico",
            "home_score": "2",
            "away_score": "0",
            "tournament": "Friendly",
        },
        {
            "date": "2024-02-01",
            "home_team": "Canada",
            "away_team": "Mexico",
            "home_score": "1",
            "away_score": "1",
            "tournament": "Friendly",
        },
    ]
    matches = parse_international_results_training_matches(rows)

    examples = build_training_examples(matches)

    assert examples[0].features["home_matches"] == 0
    assert examples[0].features["away_matches"] == 0
    assert examples[1].features["home_matches"] == 1
    assert examples[1].features["away_matches"] == 1
    assert examples[1].features["home_gf_avg"] == pytest.approx(2.0)
    assert examples[1].features["away_ga_avg"] == pytest.approx(2.0)


def test_learned_model_training_persists_artifact_and_prediction_shape(tmp_path):
    rows = []
    for idx in range(80):
        rows.append(
            {
                "date": f"2024-01-{(idx % 28) + 1:02d}",
                "home_team": "Strong",
                "away_team": "Weak",
                "home_score": "3",
                "away_score": "0",
                "tournament": "Friendly",
            }
        )
        rows.append(
            {
                "date": f"2024-02-{(idx % 28) + 1:02d}",
                "home_team": "Weak",
                "away_team": "Strong",
                "home_score": "0",
                "away_score": "2",
                "tournament": "Friendly",
            }
        )
    matches = parse_international_results_training_matches(rows)
    model_path = tmp_path / "learned_goal_model.joblib"

    metadata = train_learned_goal_model(matches, model_path, min_examples=40)
    learned = load_learned_goal_model(model_path)

    assert metadata["promoted"] is True
    assert model_path.exists()
    assert learned is not None
    prediction = predict_match(
        "fixture-1",
        TeamFeatures("strong", "Strong", 1.45, 0.80, 1900, 0.75, 0.75),
        TeamFeatures("weak", "Weak", 0.75, 1.25, 1400, 0.30, 0.35),
        learned_model=learned,
    )
    assert prediction["model_version"] == "learned-poisson-dixon-coles-v1"
    assert sum(prediction["wdl"].values()) == pytest.approx(1.0)
    assert sum(cell["probability"] for cell in prediction["score_matrix"]) == pytest.approx(1.0)
    assert prediction["expected_goals"]["home"] > prediction["expected_goals"]["away"]


def test_missing_learned_model_falls_back_to_v2():
    prediction = predict_match(
        "fixture-1",
        TeamFeatures("a", "A", 1.1, 0.95, 1700, 0.55, 0.55),
        TeamFeatures("b", "B", 1.0, 1.05, 1650, 0.50, 0.50),
        learned_model=None,
    )

    assert prediction["model_version"] == "dixon-coles-poisson-v2"


def test_admin_train_writes_learned_metadata_and_api_can_load_model(tmp_path):
    model_path = tmp_path / "model.json"
    client = TestClient(create_app(database_url=":memory:", model_artifact_path=model_path))
    repository: Repository = client.app.state.repository
    matches = parse_international_results_training_matches(
        [
            {
                "date": f"2024-03-{(idx % 28) + 1:02d}",
                "home_team": "Canada",
                "away_team": "Mexico",
                "home_score": "2",
                "away_score": "0",
                "tournament": "Friendly",
            }
            for idx in range(70)
        ]
        + [
            {
                "date": f"2024-04-{(idx % 28) + 1:02d}",
                "home_team": "Mexico",
                "away_team": "Canada",
                "home_score": "0",
                "away_score": "2",
                "tournament": "Friendly",
            }
            for idx in range(70)
        ]
    )
    repository.save_training_matches(matches)

    result = client.post("/admin/train").json()
    artifact = json.loads(model_path.read_text(encoding="utf-8"))

    assert result["model_type"] == "learned-poisson-dixon-coles-v1"
    assert result["learned_model"]["promoted"] is True
    assert artifact["learned_model"]["promoted"] is True
    assert (tmp_path / "learned_goal_model.joblib").exists()
