from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Repository
from app.learned_model import parse_international_results_training_matches
from app.recent_form import aggregate_recent_form_profiles, load_recent_results_rows
from app.settings import load_env_file


def main() -> None:
    load_env_file()
    rows = load_recent_results_rows()
    profiles = aggregate_recent_form_profiles(rows)
    repository = Repository()
    repository.save_stat_profiles(profiles["team_profiles"], profiles["player_profiles"])
    training_matches = parse_international_results_training_matches(rows)
    repository.save_training_matches(training_matches)
    print(f"synced {len(profiles['team_profiles'])} recent-form team profiles from international results")
    print(f"stored {len(training_matches)} match-level training rows from international results")


if __name__ == "__main__":
    main()
