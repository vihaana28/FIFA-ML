from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtesting import write_backtest_metrics
from app.db import Repository
from app.settings import load_env_file
from app.training import write_model_artifact


def main() -> None:
    load_env_file()
    repository = Repository()
    artifact = write_model_artifact(repository)
    metrics = write_backtest_metrics(repository, "data/model/backtest.json")
    print(f"wrote data/model/model.json with {artifact['team_count']} teams")
    print(f"wrote data/model/backtest.json with {metrics['sample_matches']} sample matches")


if __name__ == "__main__":
    main()
