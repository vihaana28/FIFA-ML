from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db import Repository
from app.sync_service import SyncService


class FakeFootballDataClient:
    enabled = True

    def __init__(self, fixtures: list[dict] | None = None, error: Exception | None = None):
        self.fixtures = fixtures or []
        self.error = error
        self.calls = 0

    def world_cup_matches(self) -> list[dict]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.fixtures


def _fixture(status: str = "TIMED", score: dict | None = None, kickoff: str = "2026-06-13T19:00:00Z") -> dict:
    return {
        "id": "football-data-1",
        "provider": "football-data",
        "provider_fixture_id": "1",
        "home_team_id": "769",
        "away_team_id": "774",
        "home_team": "Mexico",
        "away_team": "South Africa",
        "kickoff": kickoff,
        "venue": "",
        "stage": "GROUP_A - GROUP_STAGE",
        "status": status,
        "score": score or {"home": None, "away": None, "winner": None},
    }


def test_sync_service_updates_finished_match_stats_and_invalidates_prediction():
    repository = Repository(":memory:")
    repository.replace_fixtures([_fixture()])
    repository.save_prediction("football-data-1", {"fixture_id": "football-data-1", "stale": True})
    client = FakeFootballDataClient([_fixture(status="FINISHED", score={"home": 2, "away": 0, "winner": "HOME_TEAM"})])
    service = SyncService(
        repository=repository,
        football_data_client=client,
        now=lambda: datetime(2026, 6, 13, 21, tzinfo=timezone.utc),
    )

    result = service.sync(force=True)

    detail = repository.get_fixture("football-data-1")
    assert result["changed_fixture_ids"] == ["football-data-1"]
    assert detail["status"] == "FINISHED"
    assert detail["score"] == {"home": 2, "away": 0, "winner": "HOME_TEAM"}
    assert repository.get_team_stats("769")["points"] == 3
    assert repository.get_saved_prediction("football-data-1") is None


def test_sync_service_marks_stale_status_when_provider_fails():
    repository = Repository(":memory:")
    repository.replace_fixtures([_fixture()])
    client = FakeFootballDataClient(error=RuntimeError("quota exceeded"))
    service = SyncService(
        repository=repository,
        football_data_client=client,
        now=lambda: datetime(2026, 6, 13, 21, tzinfo=timezone.utc),
    )

    with pytest.raises(RuntimeError):
        service.sync(force=False)

    status = service.status()
    assert status["last_error"] == "quota exceeded"
    assert status["stale"] is True
    assert status["running"] is False


def test_sync_service_skips_provider_outside_live_window_without_force():
    repository = Repository(":memory:")
    repository.replace_fixtures([_fixture(kickoff="2026-07-01T19:00:00Z")])
    client = FakeFootballDataClient([_fixture(status="FINISHED", score={"home": 2, "away": 0, "winner": "HOME_TEAM"})])
    service = SyncService(
        repository=repository,
        football_data_client=client,
        now=lambda: datetime(2026, 6, 13, 12, tzinfo=timezone.utc),
    )

    result = service.sync(force=False)

    assert result["status"] == "skipped"
    assert client.calls == 0
    assert repository.get_fixture("football-data-1")["status"] == "TIMED"
