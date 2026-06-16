from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Repository
from app.elo import aggregate_elo_profiles, load_elo_rows
from app.settings import load_env_file


def main() -> None:
    load_env_file()
    repository = Repository()
    rows = load_elo_rows()
    profiles = aggregate_elo_profiles(rows, repository.list_fixtures())
    repository.save_stat_profiles(profiles["team_profiles"], profiles["player_profiles"])
    print(f"ingested {len(profiles['team_profiles'])} World Football Elo team profiles")


if __name__ == "__main__":
    main()
