from __future__ import annotations

import csv
import os
import urllib.request
from pathlib import Path

from app.db import Repository
from app.learned_model import parse_international_results_training_matches


DEFAULT_RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
DEFAULT_TRAINING_MATCH_LIMIT = 1200


def _training_source(source: str | None = None) -> str:
    return source or os.getenv("TRAINING_RESULTS_CSV") or os.getenv("INTERNATIONAL_RESULTS_CSV") or DEFAULT_RESULTS_URL


def _training_match_limit() -> int:
    value = os.getenv("TRAINING_MATCH_LIMIT")
    if not value:
        return DEFAULT_TRAINING_MATCH_LIMIT
    try:
        return max(1, int(value))
    except ValueError:
        return DEFAULT_TRAINING_MATCH_LIMIT


def load_historical_training_rows(source: str | None = None) -> tuple[str, list[dict]]:
    selected_source = _training_source(source)
    if selected_source.startswith(("http://", "https://")):
        with urllib.request.urlopen(selected_source, timeout=45) as response:
            text = response.read().decode("utf-8")
        return selected_source, list(csv.DictReader(text.splitlines()))

    path = Path(selected_source)
    if not path.exists():
        return selected_source, []
    with path.open(newline="", encoding="utf-8") as handle:
        return selected_source, list(csv.DictReader(handle))


def sync_historical_training_data(repository: Repository, source: str | None = None) -> dict:
    limit = _training_match_limit()
    existing = repository.count_training_matches()
    if existing >= limit:
        return {
            "status": "training-data-skipped",
            "source": "existing-db",
            "rows": 0,
            "matches": existing,
            "saved": 0,
            "limit": limit,
            "message": "Historical training data already loaded.",
        }
    selected_source, rows = load_historical_training_rows(source)
    matches = parse_international_results_training_matches(rows)
    if len(matches) > limit:
        matches = matches[-limit:]
    saved = repository.save_training_matches(matches)
    return {
        "status": "training-data-synced",
        "source": selected_source,
        "rows": len(rows),
        "matches": len(matches),
        "saved": saved,
        "limit": limit,
    }
