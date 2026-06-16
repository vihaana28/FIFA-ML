from __future__ import annotations

import json
import os
import urllib.request
from typing import Iterable

from app.providers import slugify


def _new_team_profile(team_name: str) -> dict:
    return {
        "team_id": slugify(team_name),
        "team_name": team_name,
        "source": "StatsBomb Open Data",
        "matches": 0,
        "shots": 0,
        "goals": 0,
        "xg_for": 0.0,
        "passes": 0,
        "pressures": 0,
        "lineup_players": 0,
    }


def _new_player_profile(player_id: str, player_name: str, team_name: str) -> dict:
    return {
        "player_id": str(player_id),
        "player_name": player_name,
        "team_id": slugify(team_name),
        "team_name": team_name,
        "source": "StatsBomb Open Data",
        "shots": 0,
        "goals": 0,
        "assists": 0,
        "xg": 0.0,
        "passes": 0,
        "pressures": 0,
        "lineup_appearances": 0,
    }


def aggregate_statsbomb_match(match: dict, events: list[dict], lineups: list[dict]) -> dict[str, dict]:
    teams = {
        slugify(match["home_team"]["home_team_name"]): _new_team_profile(match["home_team"]["home_team_name"]),
        slugify(match["away_team"]["away_team_name"]): _new_team_profile(match["away_team"]["away_team_name"]),
    }
    players: dict[str, dict] = {}

    for lineup in lineups:
        team_name = lineup.get("team_name") or lineup.get("team", {}).get("name")
        if not team_name:
            continue
        team_id = slugify(team_name)
        teams.setdefault(team_id, _new_team_profile(team_name))
        teams[team_id]["lineup_players"] += len(lineup.get("lineup", []))
        for player in lineup.get("lineup", []):
            player_id = str(player.get("player_id") or player.get("player", {}).get("id"))
            player_name = player.get("player_name") or player.get("player", {}).get("name") or player_id
            players.setdefault(player_id, _new_player_profile(player_id, player_name, team_name))
            players[player_id]["lineup_appearances"] += 1

    for team in teams.values():
        team["matches"] += 1

    for event in events:
        event_type = (event.get("type") or {}).get("name")
        team_name = (event.get("team") or {}).get("name")
        if not team_name:
            continue
        team_id = slugify(team_name)
        teams.setdefault(team_id, _new_team_profile(team_name))
        player = event.get("player") or {}
        player_id = str(player.get("id") or "unknown")
        player_name = player.get("name") or player_id
        players.setdefault(player_id, _new_player_profile(player_id, player_name, team_name))

        if event_type == "Shot":
            xg = float((event.get("shot") or {}).get("statsbomb_xg") or 0)
            outcome = ((event.get("shot") or {}).get("outcome") or {}).get("name")
            teams[team_id]["shots"] += 1
            teams[team_id]["xg_for"] += xg
            players[player_id]["shots"] += 1
            players[player_id]["xg"] += xg
            if outcome == "Goal":
                teams[team_id]["goals"] += 1
                players[player_id]["goals"] += 1
        elif event_type == "Pass":
            teams[team_id]["passes"] += 1
            players[player_id]["passes"] += 1
            if (event.get("pass") or {}).get("goal_assist"):
                players[player_id]["assists"] += 1
        elif event_type == "Pressure":
            teams[team_id]["pressures"] += 1
            players[player_id]["pressures"] += 1

    return {"teams": teams, "players": players}


def merge_stat_profiles(profiles: Iterable[dict[str, dict]]) -> dict[str, list[dict]]:
    teams: dict[str, dict] = {}
    players: dict[str, dict] = {}
    for profile in profiles:
        for team_id, row in profile["teams"].items():
            if team_id not in teams:
                teams[team_id] = {**row}
                continue
            target = teams[team_id]
            for key in ("matches", "shots", "goals", "xg_for", "passes", "pressures", "lineup_players"):
                target[key] += row.get(key, 0)
        for player_id, row in profile["players"].items():
            if player_id not in players:
                players[player_id] = {**row}
                continue
            target = players[player_id]
            for key in ("shots", "goals", "assists", "xg", "passes", "pressures", "lineup_appearances"):
                target[key] += row.get(key, 0)
    return {"team_profiles": list(teams.values()), "player_profiles": list(players.values())}


def _new_result_profile(team_id: str, team_name: str) -> dict:
    return {
        "team_id": team_id,
        "team_name": team_name,
        "source": "football-data.org Results",
        "matches": 0,
        "goals": 0,
        "goals_against": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "points": 0,
        "shots": 0,
        "xg_for": 0.0,
        "passes": 0,
        "pressures": 0,
        "lineup_players": 0,
    }


def aggregate_result_profiles(fixtures: list[dict]) -> dict[str, list[dict]]:
    profiles: dict[str, dict] = {}

    for fixture in fixtures:
        score = fixture.get("score") or {}
        home_goals = score.get("home")
        away_goals = score.get("away")
        if fixture.get("status") != "FINISHED" or home_goals is None or away_goals is None:
            continue

        home_id = str(fixture["home_team_id"])
        away_id = str(fixture["away_team_id"])
        home = profiles.setdefault(home_id, _new_result_profile(home_id, fixture["home_team"]))
        away = profiles.setdefault(away_id, _new_result_profile(away_id, fixture["away_team"]))

        home["matches"] += 1
        away["matches"] += 1
        home["goals"] += int(home_goals)
        home["goals_against"] += int(away_goals)
        away["goals"] += int(away_goals)
        away["goals_against"] += int(home_goals)

        if home_goals > away_goals:
            home["wins"] += 1
            home["points"] += 3
            away["losses"] += 1
        elif home_goals < away_goals:
            away["wins"] += 1
            away["points"] += 3
            home["losses"] += 1
        else:
            home["draws"] += 1
            away["draws"] += 1
            home["points"] += 1
            away["points"] += 1

    return {"team_profiles": list(profiles.values()), "player_profiles": []}


class StatsBombOpenDataClient:
    base_url = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"

    def get_json(self, path: str) -> list | dict:
        with urllib.request.urlopen(f"{self.base_url}/{path}", timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def competitions(self) -> list[dict]:
        return self.get_json("competitions.json")

    @staticmethod
    def world_cup_competitions(competitions: list[dict]) -> list[dict]:
        rows = [
            {
                "competition_id": int(item["competition_id"]),
                "season_id": int(item["season_id"]),
                "season_name": str(item["season_name"]),
            }
            for item in competitions
            if item.get("competition_name") == "FIFA World Cup" and str(item.get("season_name")) in {"2018", "2022"}
        ]
        return sorted(rows, key=lambda item: item["season_name"], reverse=True)

    def matches(self, competition_id: int, season_id: int) -> list[dict]:
        return self.get_json(f"matches/{competition_id}/{season_id}.json")

    def events(self, match_id: int) -> list[dict]:
        return self.get_json(f"events/{match_id}.json")

    def lineups(self, match_id: int) -> list[dict]:
        return self.get_json(f"lineups/{match_id}.json")

    def world_cup_profiles(self, match_limit: int | None = None) -> dict[str, list[dict]]:
        profiles = []
        remaining = match_limit or int(os.getenv("STATSBOMB_MATCH_LIMIT", "32"))
        for competition in self.world_cup_competitions(self.competitions()):
            for match in self.matches(competition["competition_id"], competition["season_id"]):
                if remaining <= 0:
                    break
                match_id = int(match["match_id"])
                profiles.append(aggregate_statsbomb_match(match, self.events(match_id), self.lineups(match_id)))
                remaining -= 1
            if remaining <= 0:
                break
        return merge_stat_profiles(profiles)

