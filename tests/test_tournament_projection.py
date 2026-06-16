from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import Repository
from app.main import create_app
from app.tournament_projection import build_tournament_projection


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
