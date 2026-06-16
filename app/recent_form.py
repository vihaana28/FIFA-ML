from __future__ import annotations

import csv
import os
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from app.providers import slugify


CURRENT_WORLD_CUP_WEIGHT = 1.0
COMPETITIVE_WEIGHT = 0.75
FRIENDLY_WEIGHT = 0.35
OLD_MATCH_MULTIPLIER = 0.60


def _parse_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _weight_for_match(tournament: str, match_date: date, reference: date) -> tuple[float, str]:
    name = tournament.strip().lower()
    if name == "friendly":
        weight = FRIENDLY_WEIGHT
        kind = "friendly"
    elif name == "fifa world cup" and match_date.year >= 2026:
        weight = CURRENT_WORLD_CUP_WEIGHT
        kind = "current_world_cup"
    else:
        weight = COMPETITIVE_WEIGHT
        kind = "competitive"
    if (reference - match_date).days > 730:
        weight *= OLD_MATCH_MULTIPLIER
    return weight, kind


def _new_profile(team_name: str) -> dict:
    return {
        "team_id": slugify(team_name),
        "team_name": team_name,
        "source": "International Results + Friendlies",
        "matches": 0,
        "goals": 0,
        "goals_against": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "points": 0,
        "clean_sheets": 0,
        "scoring_matches": 0,
        "friendly_matches": 0,
        "competitive_matches": 0,
        "current_world_cup_matches": 0,
        "weighted_matches": 0.0,
        "weighted_goals": 0.0,
        "weighted_goals_against": 0.0,
        "weighted_points": 0.0,
        "recent_form_score": 0.0,
        "attack_multiplier": 1.0,
        "defense_multiplier": 1.0,
        "shots": 0,
        "xg_for": 0.0,
        "passes": 0,
        "pressures": 0,
        "lineup_players": 0,
    }


def _apply_result(profile: dict, goals_for: int, goals_against: int, weight: float, kind: str) -> None:
    profile["matches"] += 1
    profile["goals"] += goals_for
    profile["goals_against"] += goals_against
    profile["weighted_matches"] += weight
    profile["weighted_goals"] += goals_for * weight
    profile["weighted_goals_against"] += goals_against * weight
    if goals_against == 0:
        profile["clean_sheets"] += 1
    if goals_for > 0:
        profile["scoring_matches"] += 1
    if kind == "friendly":
        profile["friendly_matches"] += 1
    elif kind == "current_world_cup":
        profile["current_world_cup_matches"] += 1
        profile["competitive_matches"] += 1
    else:
        profile["competitive_matches"] += 1
    if goals_for > goals_against:
        profile["wins"] += 1
        profile["points"] += 3
        profile["weighted_points"] += 3 * weight
    elif goals_for < goals_against:
        profile["losses"] += 1
    else:
        profile["draws"] += 1
        profile["points"] += 1
        profile["weighted_points"] += weight


def _finalize(profile: dict) -> dict:
    weighted_matches = max(0.01, float(profile["weighted_matches"]))
    goals_for = float(profile["weighted_goals"]) / weighted_matches
    goals_against = float(profile["weighted_goals_against"]) / weighted_matches
    points_rate = float(profile["weighted_points"]) / (weighted_matches * 3)
    scoring_rate = float(profile["scoring_matches"]) / max(1, int(profile["matches"]))
    clean_sheet_rate = float(profile["clean_sheets"]) / max(1, int(profile["matches"]))
    profile["recent_form_score"] = max(0.05, min(0.95, (points_rate * 0.55) + (scoring_rate * 0.25) + (clean_sheet_rate * 0.20)))
    profile["attack_multiplier"] = max(0.70, min(1.45, goals_for / 1.35))
    profile["defense_multiplier"] = max(0.75, min(1.35, goals_against / 1.15))
    for key in ("weighted_matches", "weighted_goals", "weighted_goals_against", "weighted_points", "recent_form_score", "attack_multiplier", "defense_multiplier"):
        profile[key] = round(float(profile[key]), 4)
    return profile


def aggregate_recent_form_profiles(rows: Iterable[dict], reference_date: str | None = None, max_matches: int = 20) -> dict[str, list[dict]]:
    reference = _parse_date(reference_date or os.getenv("RECENT_FORM_REFERENCE_DATE", "")) or date.today()
    usable_rows = []
    for row in rows:
        match_date = _parse_date(str(row.get("date", "")))
        if not match_date or match_date > reference:
            continue
        try:
            home_score = int(row.get("home_score", ""))
            away_score = int(row.get("away_score", ""))
        except (TypeError, ValueError):
            continue
        usable_rows.append((match_date, row, home_score, away_score))
    usable_rows.sort(key=lambda item: item[0], reverse=True)

    profiles: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for match_date, row, home_score, away_score in usable_rows:
        home = str(row.get("home_team", "")).strip()
        away = str(row.get("away_team", "")).strip()
        if not home or not away:
            continue
        home_id = slugify(home)
        away_id = slugify(away)
        if counts.get(home_id, 0) >= max_matches and counts.get(away_id, 0) >= max_matches:
            continue
        weight, kind = _weight_for_match(str(row.get("tournament", "")), match_date, reference)
        if counts.get(home_id, 0) < max_matches:
            counts[home_id] = counts.get(home_id, 0) + 1
            _apply_result(profiles.setdefault(home_id, _new_profile(home)), home_score, away_score, weight, kind)
        if counts.get(away_id, 0) < max_matches:
            counts[away_id] = counts.get(away_id, 0) + 1
            _apply_result(profiles.setdefault(away_id, _new_profile(away)), away_score, home_score, weight, kind)

    return {"team_profiles": [_finalize(profile) for profile in profiles.values()], "player_profiles": []}


def load_recent_results_rows(path: str | Path | None = None) -> list[dict]:
    source = str(path or os.getenv("INTERNATIONAL_RESULTS_CSV", "data/raw/international_results.csv"))
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as response:
            text = response.read().decode("utf-8")
        return list(csv.DictReader(text.splitlines()))
    local_path = Path(source)
    if not local_path.exists():
        return []
    with local_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
