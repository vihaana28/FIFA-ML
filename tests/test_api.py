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


def test_cron_sync_requires_bearer_secret(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    client = TestClient(create_app(database_url=":memory:"))

    missing = client.post("/admin/cron/sync")
    wrong = client.post("/admin/cron/sync", headers={"Authorization": "Bearer wrong"})

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_cron_sync_runs_force_sync_and_persists_status(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    client = TestClient(create_app(database_url=":memory:"))
    calls = []

    class FakeSyncService:
        def sync(self, force: bool = False, include_odds: bool = False) -> dict:
            calls.append({"force": force, "include_odds": include_odds})
            return {
                "enabled": True,
                "running": False,
                "last_sync_at": "2026-06-18T10:00:00Z",
                "last_success_at": "2026-06-18T10:00:00Z",
                "last_error": None,
                "fixture_source": "football-data.org",
                "odds_source": "The Odds API",
                "current_result_team_profiles": 2,
                "next_sync_at": "2026-06-18T10:05:00Z",
                "stale": False,
                "status": "synced",
                "changed_fixture_ids": [],
            }

    client.app.state.sync_service = FakeSyncService()

    response = client.post("/admin/cron/sync", headers={"Authorization": "Bearer test-secret"})

    assert response.status_code == 200
    assert response.json()["status"] == "synced"
    assert calls == [{"force": True, "include_odds": True}]
    assert client.app.state.repository.get_sync_status()["fixture_source"] == "football-data.org"


def test_cron_train_runs_sync_and_persists_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    model_path = tmp_path / "model.json"
    client = TestClient(create_app(database_url=":memory:", model_artifact_path=model_path))

    class FakeSyncService:
        def sync(self, force: bool = False, include_odds: bool = False) -> dict:
            return {
                "enabled": True,
                "running": False,
                "last_sync_at": "2026-06-18T10:00:00Z",
                "last_success_at": "2026-06-18T10:00:00Z",
                "last_error": None,
                "fixture_source": "football-data.org",
                "odds_source": "The Odds API",
                "current_result_team_profiles": 2,
                "next_sync_at": "2026-06-18T10:05:00Z",
                "stale": False,
                "status": "synced",
                "changed_fixture_ids": [],
            }

    client.app.state.sync_service = FakeSyncService()

    response = client.post("/admin/cron/train", headers={"Authorization": "Bearer test-secret"})

    assert response.status_code == 200
    assert response.json()["status"] == "trained"
    assert client.app.state.repository.get_model_artifact("model.json")["payload"]["team_count"] >= 1
    assert client.app.state.repository.get_model_artifact("backtest.json")["payload"]["sample_matches"] >= 0
