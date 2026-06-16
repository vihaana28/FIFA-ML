from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Repository
from app.settings import load_env_file
from app.stats_sources import StatsBombOpenDataClient


def main() -> None:
    load_env_file()
    repository = Repository()
    profiles = StatsBombOpenDataClient().world_cup_profiles()
    repository.save_stat_profiles(profiles["team_profiles"], profiles["player_profiles"])
    result_profiles = repository.refresh_current_result_stats()
    print(
        "synced "
        f"{len(profiles['team_profiles'])} team stat profiles and "
        f"{len(profiles['player_profiles'])} player stat profiles from StatsBomb Open Data; "
        f"refreshed {result_profiles['team_profiles']} current result stat profiles"
    )


if __name__ == "__main__":
    main()
