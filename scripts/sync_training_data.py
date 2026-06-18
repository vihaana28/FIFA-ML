import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Repository
from app.settings import load_env_file
from app.training_data import sync_historical_training_data


def main() -> None:
    load_env_file()
    result = sync_historical_training_data(Repository())
    print(f"stored {result['saved']} match-level training rows from {result['source']}")


if __name__ == "__main__":
    main()
