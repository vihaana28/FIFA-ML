from __future__ import annotations

import csv
from datetime import date

from app.db import Repository
from app.learned_model import TrainingMatch
from app.training_data import sync_historical_training_data


def _write_results_csv(path, count: int) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "home_team", "away_team", "home_score", "away_score", "tournament", "neutral"],
        )
        writer.writeheader()
        for index in range(count):
            writer.writerow(
                {
                    "date": f"2020-01-{(index % 28) + 1:02d}",
                    "home_team": f"Home {index}",
                    "away_team": f"Away {index}",
                    "home_score": index % 4,
                    "away_score": (index + 1) % 4,
                    "tournament": "Friendly",
                    "neutral": "FALSE",
                }
            )


def test_sync_historical_training_data_limits_recent_matches(monkeypatch, tmp_path):
    repository = Repository(":memory:")
    csv_path = tmp_path / "results.csv"
    _write_results_csv(csv_path, 5)
    monkeypatch.setenv("TRAINING_MATCH_LIMIT", "2")

    result = sync_historical_training_data(repository, source=str(csv_path))

    stored = repository.list_training_matches()
    assert result["rows"] == 5
    assert result["matches"] == 2
    assert result["saved"] == 2
    assert [match.home_team for match in stored] == ["Home 3", "Home 4"]


def test_sync_historical_training_data_skips_when_limit_already_loaded(monkeypatch, tmp_path):
    repository = Repository(":memory:")
    repository.save_training_matches(
        [
            TrainingMatch(
                match_date=date(2020, 1, 1),
                home_team="Existing A",
                away_team="Existing B",
                home_score=1,
                away_score=0,
                tournament="Friendly",
                neutral=False,
                source="martj42/international_results",
            )
        ]
    )
    csv_path = tmp_path / "results.csv"
    _write_results_csv(csv_path, 5)
    monkeypatch.setenv("TRAINING_MATCH_LIMIT", "1")

    result = sync_historical_training_data(repository, source=str(csv_path))

    assert result["status"] == "training-data-skipped"
    assert result["saved"] == 0
    assert repository.count_training_matches() == 1
