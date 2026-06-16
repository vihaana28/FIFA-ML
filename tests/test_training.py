from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.db import Repository
from app.main import create_app
from app.training import build_model_artifact


def test_model_artifact_builder_includes_all_fixture_teams():
    repository = Repository(":memory:")

    artifact = build_model_artifact(repository, generated_at="2026-06-13T00:00:00Z")

    assert artifact["team_count"] == 48
    assert len(artifact["teams"]) == 48
    assert artifact["feature_weights"]["friendly"] < artifact["feature_weights"]["competitive"]


def test_admin_train_writes_full_team_artifact(tmp_path):
    model_path = tmp_path / "model.json"
    client = TestClient(create_app(database_url=":memory:", model_artifact_path=model_path))

    result = client.post("/admin/train").json()
    payload = json.loads(model_path.read_text(encoding="utf-8"))

    assert result["team_count"] == 48
    assert payload["team_count"] == 48
    assert len(payload["teams"]) == 48


def test_model_artifact_endpoint_returns_summary(tmp_path):
    model_path = tmp_path / "model.json"
    client = TestClient(create_app(database_url=":memory:", model_artifact_path=model_path))
    client.post("/admin/train")

    summary = client.get("/model/artifact").json()

    assert summary["team_count"] == 48
    assert "generated_at" in summary


def test_recent_form_ingest_changes_prediction_features():
    client = TestClient(create_app(database_url=":memory:"))
    fixture = next(item for item in client.get("/fixtures").json() if item["home_team"] == "Canada")
    before = client.get(f"/predictions/{fixture['id']}").json()

    client.post(
        "/admin/stats/ingest",
        json={
            "team_profiles": [
                {
                    "team_id": fixture["home_team_id"],
                    "team_name": "Canada",
                    "source": "International Results + Friendlies",
                    "matches": 3,
                    "weighted_matches": 2.25,
                    "weighted_goals": 9.0,
                    "weighted_goals_against": 1.0,
                    "weighted_points": 6.75,
                    "recent_form_score": 0.82,
                    "attack_multiplier": 1.45,
                    "defense_multiplier": 0.88,
                    "friendly_matches": 1,
                    "competitive_matches": 2,
                }
            ],
            "player_profiles": [],
        },
    )
    after = client.get(f"/predictions/{fixture['id']}").json()

    assert after["features"]["home"]["recent_form"] > before["features"]["home"]["recent_form"]
    assert after["expected_goals"]["home"] != before["expected_goals"]["home"]
