from __future__ import annotations

import sqlite3
import sys
from types import SimpleNamespace

from app.db import Repository


def test_repository_uses_local_sqlite_without_turso_env(monkeypatch, tmp_path):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    repository = Repository(str(tmp_path / "local.sqlite3"))

    assert repository.storage_backend == "sqlite"
    assert repository.get_fixture(repository.list_fixtures()[0]["id"])


def test_repository_uses_turso_when_credentials_exist(monkeypatch):
    calls = []

    def connect(*, database: str, auth_token: str):
        calls.append({"database": database, "auth_token": auth_token})
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://fifa-db.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "test-token")
    monkeypatch.setitem(sys.modules, "libsql", SimpleNamespace(connect=connect))

    repository = Repository()

    assert repository.storage_backend == "turso"
    assert calls == [{"database": "libsql://fifa-db.turso.io", "auth_token": "test-token"}]


def test_sync_status_persists_across_repository_instances(tmp_path):
    db_path = tmp_path / "status.sqlite3"
    first = Repository(str(db_path))
    first.save_sync_status(
        {
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
        }
    )

    second = Repository(str(db_path))

    assert second.get_sync_status()["fixture_source"] == "football-data.org"
    assert second.get_sync_status()["current_result_team_profiles"] == 2


def test_model_artifacts_persist_json_and_binary_payloads(tmp_path):
    repository = Repository(str(tmp_path / "artifacts.sqlite3"))

    repository.save_model_artifact("model.json", {"team_count": 48}, content_type="application/json")
    repository.save_model_artifact(
        "learned_goal_model.joblib",
        b"joblib-bytes",
        content_type="application/octet-stream",
        metadata={"model_type": "learned"},
    )

    assert repository.get_model_artifact("model.json")["payload"] == {"team_count": 48}
    learned = repository.get_model_artifact("learned_goal_model.joblib")
    assert learned["payload"] == b"joblib-bytes"
    assert learned["metadata"] == {"model_type": "learned"}
