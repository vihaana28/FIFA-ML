from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backtesting import write_backtest_metrics
from app.db import Repository
from app.settings import load_env_file


def main() -> None:
    load_env_file()
    metrics = write_backtest_metrics(Repository(), "data/model/backtest.json")
    print(f"wrote data/model/backtest.json with {metrics['sample_matches']} sample matches")


if __name__ == "__main__":
    main()
