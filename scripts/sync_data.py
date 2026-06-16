from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Repository
from app.settings import load_env_file
from app.sync_service import SyncService


def main() -> None:
    load_env_file()
    service = SyncService(Repository())
    result = service.sync(force=True, include_odds=True)
    print(
        f"synced {result['fixtures']} fixtures from {result['fixture_source']}; "
        f"saved {result['odds_saved']} odds snapshots; "
        f"refreshed {result['current_result_team_profiles']} current result stat profiles"
    )


if __name__ == "__main__":
    main()
