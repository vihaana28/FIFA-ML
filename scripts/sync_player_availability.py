from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Repository
from app.player_availability import aggregate_player_availability, load_player_availability_rows
from app.settings import load_env_file


def main() -> None:
    load_env_file()
    rows = load_player_availability_rows()
    profiles = aggregate_player_availability(rows)
    Repository().save_stat_profiles(profiles["team_profiles"], profiles["player_profiles"])
    print(
        "ingested "
        f"{len(profiles['team_profiles'])} player-availability team profiles and "
        f"{len(profiles['player_profiles'])} player rows"
    )


if __name__ == "__main__":
    main()
