from __future__ import annotations

import csv
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Repository
from app.learned_model import parse_international_results_training_matches
from app.settings import load_env_file


DEFAULT_RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"


def _load_rows() -> list[dict]:
    source = os.getenv("TRAINING_RESULTS_CSV") or os.getenv("INTERNATIONAL_RESULTS_CSV") or DEFAULT_RESULTS_URL
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=45) as response:
            text = response.read().decode("utf-8")
        return list(csv.DictReader(text.splitlines()))
    path = Path(source)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    load_env_file()
    rows = _load_rows()
    matches = parse_international_results_training_matches(rows)
    saved = Repository().save_training_matches(matches)
    print(f"stored {saved} match-level training rows")


if __name__ == "__main__":
    main()
