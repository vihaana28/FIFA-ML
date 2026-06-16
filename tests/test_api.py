from fastapi.testclient import TestClient

from app.main import create_app


def test_api_serves_fixtures_predictions_and_parlay():
    client = TestClient(create_app(database_url=":memory:"))

    fixtures = client.get("/fixtures").json()
    assert fixtures

    fixture_id = fixtures[0]["id"]
    detail = client.get(f"/fixtures/{fixture_id}").json()
    prediction = client.get(f"/predictions/{fixture_id}").json()
    parlay = client.post(
        "/bets/parlay",
        json={
            "stake": 10,
            "legs": [
                {
                    "fixture_id": fixture_id,
                    "market": "moneyline",
                    "selection": "home",
                    "probability": prediction["wdl"]["home"],
                    "american_odds": -110,
                }
            ],
        },
    ).json()

    assert detail["id"] == fixture_id
    assert prediction["top_scores"]
    assert parlay["combined_probability"] == prediction["wdl"]["home"]


def test_api_exposes_model_metrics_and_data_sources():
    client = TestClient(create_app(database_url=":memory:"))

    metrics = client.get("/model/metrics").json()
    sources = client.get("/data/sources").json()

    assert metrics["model_type"]
    assert any(source["name"] == "API-Football" for source in sources)


def test_api_exposes_sync_status():
    client = TestClient(create_app(database_url=":memory:"))

    status = client.get("/sync/status").json()

    assert set(status) >= {
        "enabled",
        "running",
        "last_sync_at",
        "last_success_at",
        "last_error",
        "fixture_source",
        "current_result_team_profiles",
        "next_sync_at",
        "stale",
    }
