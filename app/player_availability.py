from __future__ import annotations

import csv
import os
from pathlib import Path

from app.providers import slugify


STATUS_PENALTIES = {"available": 0.0, "doubtful": 0.35, "injured": 1.0, "suspended": 1.0}


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def aggregate_player_availability(rows: list[dict]) -> dict[str, list[dict]]:
    teams: dict[str, dict] = {}
    players: list[dict] = []
    for row in rows:
        team_name = str(row.get("team", "")).strip()
        player_name = str(row.get("player", "")).strip()
        if not team_name or not player_name:
            continue
        team_id = slugify(team_name)
        status = str(row.get("status", "available")).strip().lower()
        importance = max(0.0, min(1.0, _to_float(row.get("importance"), 0.5)))
        minutes_share = max(0.0, min(1.0, _to_float(row.get("minutes_share"), 0.5)))
        attack_contribution = max(0.0, min(1.0, _to_float(row.get("attack_contribution"), 0.0)))
        defense_contribution = max(0.0, min(1.0, _to_float(row.get("defense_contribution"), 0.0)))
        penalty = STATUS_PENALTIES.get(status, 0.0) * importance * minutes_share
        team = teams.setdefault(
            team_id,
            {
                "team_id": team_id,
                "team_name": team_name,
                "source": "Player Availability",
                "matches": 0,
                "availability": 1.0,
                "attack_availability": 1.0,
                "defense_availability": 1.0,
                "missing_key_players": 0,
                "shots": 0,
                "goals": 0,
                "goals_against": 0,
                "xg_for": 0.0,
                "passes": 0,
                "pressures": 0,
                "lineup_players": 0,
            },
        )
        if penalty:
            team["missing_key_players"] += 1
            team["availability"] -= penalty * 0.20
            team["attack_availability"] -= penalty * attack_contribution * 0.35
            team["defense_availability"] -= penalty * defense_contribution * 0.30
        players.append(
            {
                "player_id": slugify(f"{team_name}-{player_name}"),
                "team_id": team_id,
                "team_name": team_name,
                "player_name": player_name,
                "source": "Player Availability",
                "status": status,
                "importance": importance,
                "minutes_share": minutes_share,
                "attack_contribution": attack_contribution,
                "defense_contribution": defense_contribution,
            }
        )
    for team in teams.values():
        team["availability"] = max(0.65, round(team["availability"], 4))
        team["attack_availability"] = max(0.65, round(team["attack_availability"], 4))
        team["defense_availability"] = max(0.65, round(team["defense_availability"], 4))
    return {"team_profiles": list(teams.values()), "player_profiles": players}


def load_player_availability_rows(path: str | Path | None = None) -> list[dict]:
    source = Path(path or os.getenv("PLAYER_AVAILABILITY_CSV", "data/raw/player_availability.csv"))
    if not source.exists():
        return []
    with source.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
