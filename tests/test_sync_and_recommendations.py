from fastapi.testclient import TestClient

from app.db import Repository
from app.main import create_app
from app.recommendations import recommend_bets


def test_repository_seeds_real_world_cup_fixtures_not_fake_games():
    repository = Repository(":memory:")
    fixtures = repository.list_fixtures()
    labels = {(fixture["home_team"], fixture["away_team"]) for fixture in fixtures}

    assert ("Canada", "Bosnia & Herzegovina") in labels
    assert ("USA", "Paraguay") in labels
    assert ("United States", "Mexico") not in labels


def test_admin_sync_reports_real_fixture_source_without_api_keys():
    client = TestClient(create_app(database_url=":memory:"))

    result = client.post("/admin/sync").json()
    fixtures = client.get("/fixtures").json()

    assert result["fixtures"] >= 72
    assert result["fixture_source"] in {"OpenFootball", "API-Football", "football-data.org"}
    assert any(
        fixture["home_team"] == "Canada" and fixture["away_team"] in {"Bosnia & Herzegovina", "Bosnia-Herzegovina"}
        for fixture in fixtures
    )


def test_recommendations_require_positive_edge_and_real_odds():
    repository = Repository(":memory:")
    fixture = next(item for item in repository.list_fixtures() if item["home_team"] == "Canada")
    repository.save_odds(
        fixture["id"],
        {"home": 260, "draw": 260, "away": 120, "source": "test-book", "last_updated": "2026-06-12T12:00:00Z"},
    )

    result = recommend_bets(repository, min_edge=0.01)

    assert result["best_singles"]
    assert all(bet["edge"] >= 0.01 for bet in result["best_singles"])
    assert all(bet["fixture_id"] == fixture["id"] for bet in result["best_singles"])
    assert result["warning"].startswith("Strategy simulator")


def test_recommendations_endpoint_returns_sections():
    client = TestClient(create_app(database_url=":memory:"))

    result = client.get("/bets/recommendations").json()

    assert set(result) >= {"best_singles", "game_parlays", "day_parlays", "avoid", "warning"}
    assert "parlay_candidates" not in result


def test_recommendations_return_game_and_day_parlays_instead_of_global_parlay():
    repository = Repository(":memory:")
    fixtures = repository.list_fixtures()[:2]
    for fixture in fixtures:
        repository.save_odds(
            fixture["id"],
            {"home": 600, "draw": 600, "away": 600, "source": "test-book", "last_updated": "2026-06-12T12:00:00Z"},
        )

    result = recommend_bets(repository, min_edge=-1)

    assert "parlay_candidates" not in result
    assert result["game_parlays"]
    assert {item["mode"] for item in result["game_parlays"]} >= {"simple", "model", "aggressive"}
    assert result["day_parlays"]
    assert {item["mode"] for item in result["day_parlays"]} >= {"simple"}


def test_recommendations_return_empty_game_parlay_reasons_without_odds():
    repository = Repository(":memory:")
    fixture = repository.list_fixtures()[0]

    result = recommend_bets(repository, min_edge=0.01)
    fixture_parlays = [item for item in result["game_parlays"] if item["fixture_id"] == fixture["id"]]

    assert {item["mode"] for item in fixture_parlays} == {"simple", "model", "aggressive"}
    assert all(item["legs"] == [] for item in fixture_parlays)
    assert all(item["reason"] for item in fixture_parlays)


def test_stats_endpoints_expose_team_and_player_profiles():
    client = TestClient(create_app(database_url=":memory:"))

    client.post(
        "/admin/stats/ingest",
        json={
            "team_profiles": [
                {"team_id": "argentina", "team_name": "Argentina", "source": "StatsBomb Open Data", "matches": 7, "xg_for": 12.5}
            ],
            "player_profiles": [
                {"player_id": "5503", "team_id": "argentina", "player_name": "Lionel Messi", "source": "StatsBomb Open Data", "xg": 4.2}
            ],
        },
    )

    teams = client.get("/stats/teams").json()
    players = client.get("/stats/players?team_id=argentina").json()

    assert teams[0]["team_name"] == "Argentina"
    assert teams[0]["source"] == "StatsBomb Open Data"
    assert players[0]["player_name"] == "Lionel Messi"


def test_fixture_detail_includes_team_stat_profiles_when_available():
    client = TestClient(create_app(database_url=":memory:"))
    fixture = next(item for item in client.get("/fixtures").json() if item["home_team"] == "Canada")
    client.post(
        "/admin/stats/ingest",
        json={
            "team_profiles": [
                {"team_id": fixture["home_team_id"], "team_name": "Canada", "source": "StatsBomb Open Data", "matches": 3, "xg_for": 4.5}
            ],
            "player_profiles": [],
        },
    )

    detail = client.get(f"/fixtures/{fixture['id']}").json()

    assert detail["home_team_stats"]["source"] == "StatsBomb Open Data"
    assert detail["home_team_stats"]["xg_for"] == 4.5


def test_repository_refreshes_current_result_stats_for_played_games():
    repository = Repository(":memory:")
    repository.replace_fixtures(
        [
            {
                "id": "football-data-537327",
                "provider": "football-data",
                "provider_fixture_id": "537327",
                "home_team_id": "769",
                "away_team_id": "774",
                "home_team": "Mexico",
                "away_team": "South Africa",
                "kickoff": "2026-06-11T19:00:00Z",
                "venue": "",
                "stage": "GROUP_A - GROUP_STAGE",
                "status": "FINISHED",
                "score": {"home": 2, "away": 0, "winner": "HOME_TEAM"},
            }
        ]
    )

    result = repository.refresh_current_result_stats()

    assert result["team_profiles"] == 2
    assert repository.get_team_stats("769")["source"] == "football-data.org Results"
    assert repository.get_team_stats("769")["goals"] == 2


def test_football_data_numeric_ids_use_team_name_priors_for_predictions():
    repository = Repository(":memory:")
    repository.replace_fixtures(
        [
            {
                "id": "football-data-usa-paraguay",
                "provider": "football-data",
                "provider_fixture_id": "1",
                "home_team_id": "771",
                "away_team_id": "761",
                "home_team": "United States",
                "away_team": "Paraguay",
                "kickoff": "2026-06-12T22:00:00Z",
                "venue": "",
                "stage": "GROUP_D - GROUP_STAGE",
                "status": "TIMED",
                "score": {"home": None, "away": None, "winner": None},
            },
            {
                "id": "football-data-qatar-switzerland",
                "provider": "football-data",
                "provider_fixture_id": "2",
                "home_team_id": "8030",
                "away_team_id": "788",
                "home_team": "Qatar",
                "away_team": "Switzerland",
                "kickoff": "2026-06-13T01:00:00Z",
                "venue": "",
                "stage": "GROUP_B - GROUP_STAGE",
                "status": "TIMED",
                "score": {"home": None, "away": None, "winner": None},
            },
        ]
    )

    usa = repository.get_team_features("771")
    paraguay = repository.get_team_features("761")
    qatar = repository.get_team_features("8030")
    switzerland = repository.get_team_features("788")

    assert usa.team_id == "771"
    assert usa.attack > paraguay.attack
    assert qatar.attack < switzerland.attack
    assert qatar.elo < switzerland.elo
