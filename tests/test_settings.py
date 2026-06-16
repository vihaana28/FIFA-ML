import os

from app.settings import load_env_file


def test_load_env_file_sets_missing_values_without_overwriting(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
FOOTBALL_DATA_TOKEN="from-file"
THE_ODDS_API_KEY=from-file-odds
EXISTING=from-file
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.delenv("FOOTBALL_DATA_TOKEN", raising=False)
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    monkeypatch.setenv("EXISTING", "from-env")

    loaded = load_env_file(env_file)

    assert loaded == 2
    assert os.environ["FOOTBALL_DATA_TOKEN"] == "from-file"
    assert os.environ["THE_ODDS_API_KEY"] == "from-file-odds"
    assert os.environ["EXISTING"] == "from-env"
