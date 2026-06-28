from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import Repository
from app.main import create_app
from app.tournament_projection import build_tournament_projection


def _fixture(
    fixture_id: str,
    home_id: str,
    away_id: str,
    home: str,
    away: str,
    stage: str,
    status: str = "TIMED",
    score: dict | None = None,
) -> dict:
    return {
        "id": fixture_id,
        "provider": "football-data",
        "provider_fixture_id": fixture_id.replace("football-data-", ""),
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team": home,
        "away_team": away,
        "kickoff": "2026-06-28T19:00:00Z",
        "venue": "Test Stadium",
        "stage": stage,
        "status": status,
        "score": score or {"home": None, "away": None, "winner": None},
    }


def test_tournament_projection_ranks_groups_and_builds_bracket():
    repository = Repository(":memory:")

    projection = build_tournament_projection(repository)

    assert projection["group_rankings"]
    group_a = next(group for group in projection["group_rankings"] if group["group"] == "Group A")
    assert len(group_a["teams"]) == 4
    assert group_a["teams"][0]["rank"] == 1
    assert group_a["teams"][0]["qualification"] in {"qualified", "best-third", "out"}
    assert projection["qualifiers_count"] == 32
    assert [round_row["round"] for round_row in projection["bracket"]] == [
        "Round of 32",
        "Round of 16",
        "Quarterfinals",
        "Semifinals",
        "Final",
    ]
    assert len(projection["bracket"][0]["matches"]) == 16
    assert projection["champion"]["team_name"]
    assert 0 <= projection["champion"]["title_probability"] <= 1


def test_tournament_projection_endpoint_returns_clean_payload():
    client = TestClient(create_app(database_url=":memory:"))

    payload = client.get("/tournament/projection").json()

    assert payload["model_version"]
    assert len(payload["group_rankings"]) == 12
    assert payload["bracket"][0]["matches"][0]["home_team"]
    assert payload["bracket"][0]["matches"][0]["winner"]


def test_tournament_projection_uses_real_knockout_fixtures_before_synthetic_bracket():
    repository = Repository(":memory:")
    repository.replace_fixtures(
        [
            _fixture("football-data-9001", "argentina", "france", "Argentina", "France", "LAST_32"),
        ]
    )

    projection = build_tournament_projection(repository)

    assert projection["bracket"][0]["round"] == "Round of 32"
    assert projection["bracket"][0]["matches"][0]["fixture_id"] == "football-data-9001"
    assert projection["bracket"][0]["matches"][0]["home_team"] == "Argentina"
    assert projection["bracket"][0]["matches"][0]["away_team"] == "France"
    assert projection["bracket"][0]["matches"][0]["status"] == "TIMED"
    assert projection["bracket"][0]["matches"][0]["source"] == "real-fixture"


def test_tournament_projection_finished_knockout_score_forces_actual_winner():
    repository = Repository(":memory:")
    repository.replace_fixtures(
        [
            _fixture(
                "football-data-9002",
                "argentina",
                "france",
                "Argentina",
                "France",
                "LAST_32",
                status="FINISHED",
                score={"home": 0, "away": 2, "winner": "AWAY_TEAM"},
            ),
        ]
    )

    projection = build_tournament_projection(repository)
    match = projection["bracket"][0]["matches"][0]

    assert match["winner"] == "France"
    assert match["winner_probability"] == 1.0
    assert match["score"] == {"home": 0, "away": 2, "winner": "AWAY_TEAM"}
