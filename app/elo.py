from __future__ import annotations

import csv
import os
from pathlib import Path

from app.providers import slugify


def _fixture_team_ids(fixtures: list[dict]) -> dict[str, str]:
    mapping = {}
    for fixture in fixtures:
        mapping[slugify(fixture["home_team"])] = fixture["home_team_id"]
        mapping[slugify(fixture["away_team"])] = fixture["away_team_id"]
    return mapping


def aggregate_elo_profiles(rows: list[dict], fixtures: list[dict]) -> dict[str, list[dict]]:
    fixture_ids = _fixture_team_ids(fixtures)
    profiles = []
    for row in rows:
        team_name = str(row.get("team") or row.get("Team") or row.get("country") or row.get("Country") or "").strip()
        if not team_name:
            continue
        try:
            rating = float(row.get("rating") or row.get("Rating") or row.get("elo") or row.get("Elo"))
        except (TypeError, ValueError):
            continue
        team_slug = slugify(team_name)
        team_id = fixture_ids.get(team_slug, team_slug)
        profiles.append(
            {
                "team_id": team_id,
                "team_name": team_name,
                "source": "World Football Elo",
                "matches": 0,
                "elo": int(round(rating)),
                "elo_strength": max(0.70, min(1.35, rating / 1800)),
                "shots": 0,
                "goals": 0,
                "goals_against": 0,
                "xg_for": 0.0,
                "passes": 0,
                "pressures": 0,
                "lineup_players": 0,
            }
        )
    return {"team_profiles": profiles, "player_profiles": []}


def load_elo_rows(path: str | Path | None = None) -> list[dict]:
    source = Path(path or os.getenv("WORLD_ELO_CSV", "data/raw/world_elo.csv"))
    if not source.exists():
        return []
    with source.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
