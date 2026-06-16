from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.model import MODEL_VERSION, predict_match


GROUP_RE = re.compile(r"GROUP[_\s-]*(?P<letter>[A-L])", re.IGNORECASE)


@dataclass
class TeamStanding:
    team_id: str
    team_name: str
    group: str
    points: float = 0.0
    goals_for: float = 0.0
    goals_against: float = 0.0
    wins: float = 0.0
    draws: float = 0.0
    losses: float = 0.0

    @property
    def goal_difference(self) -> float:
        return self.goals_for - self.goals_against


@dataclass
class BracketTeam:
    team_id: str
    team_name: str
    seed_label: str
    path_probability: float = 1.0


def _group_label(stage: str) -> str | None:
    match = GROUP_RE.search(stage or "")
    if not match:
        return None
    return f"Group {match.group('letter').upper()}"


def _sort_key(team: TeamStanding) -> tuple[float, float, float, str]:
    return (team.points, team.goal_difference, team.goals_for, _invert_name(team.team_name))


def _invert_name(name: str) -> str:
    # Keeps tuple descending for numeric fields while making names ascending deterministic.
    return "".join(chr(255 - ord(char)) for char in name.lower())


def _round(value: float) -> float:
    return round(float(value), 3)


def _apply_actual(home: TeamStanding, away: TeamStanding, home_score: int, away_score: int) -> None:
    home.goals_for += home_score
    home.goals_against += away_score
    away.goals_for += away_score
    away.goals_against += home_score
    if home_score > away_score:
        home.points += 3
        home.wins += 1
        away.losses += 1
    elif home_score < away_score:
        away.points += 3
        away.wins += 1
        home.losses += 1
    else:
        home.points += 1
        away.points += 1
        home.draws += 1
        away.draws += 1


def _apply_expected(home: TeamStanding, away: TeamStanding, prediction: dict[str, Any]) -> None:
    home_win = float(prediction["wdl"]["home"])
    draw = float(prediction["wdl"]["draw"])
    away_win = float(prediction["wdl"]["away"])
    home.points += (home_win * 3) + draw
    away.points += (away_win * 3) + draw
    home.wins += home_win
    home.draws += draw
    home.losses += away_win
    away.wins += away_win
    away.draws += draw
    away.losses += home_win
    home.goals_for += float(prediction["expected_goals"]["home"])
    home.goals_against += float(prediction["expected_goals"]["away"])
    away.goals_for += float(prediction["expected_goals"]["away"])
    away.goals_against += float(prediction["expected_goals"]["home"])


def _standing_payload(team: TeamStanding, rank: int, qualification: str) -> dict[str, Any]:
    return {
        "rank": rank,
        "team_id": team.team_id,
        "team_name": team.team_name,
        "points": _round(team.points),
        "goal_difference": _round(team.goal_difference),
        "goals_for": _round(team.goals_for),
        "goals_against": _round(team.goals_against),
        "wins": _round(team.wins),
        "draws": _round(team.draws),
        "losses": _round(team.losses),
        "qualification": qualification,
    }


def _knockout_probability(prediction: dict[str, Any]) -> tuple[str, float]:
    home = float(prediction["wdl"]["home"])
    away = float(prediction["wdl"]["away"])
    total = max(0.0001, home + away)
    if home >= away:
        return "home", home / total
    return "away", away / total


def _play_round(
    round_name: str,
    teams: list[BracketTeam],
    repository: Any,
    learned_model: Any | None,
) -> tuple[dict[str, Any], list[BracketTeam]]:
    matches = []
    winners = []
    for index in range(0, len(teams), 2):
        home = teams[index]
        away = teams[index + 1]
        prediction = predict_match(
            f"projection-{round_name.lower().replace(' ', '-')}-{index // 2 + 1}",
            repository.get_team_features(home.team_id),
            repository.get_team_features(away.team_id),
            learned_model=learned_model,
        )
        side, probability = _knockout_probability(prediction)
        winner = home if side == "home" else away
        winner = BracketTeam(
            team_id=winner.team_id,
            team_name=winner.team_name,
            seed_label=winner.seed_label,
            path_probability=winner.path_probability * probability,
        )
        winners.append(winner)
        matches.append(
            {
                "slot": index // 2 + 1,
                "home_team": home.team_name,
                "home_seed": home.seed_label,
                "away_team": away.team_name,
                "away_seed": away.seed_label,
                "winner": winner.team_name,
                "winner_probability": _round(probability),
                "expected_goals": prediction["expected_goals"],
            }
        )
    return {"round": round_name, "matches": matches}, winners


def build_tournament_projection(repository: Any, learned_model: Any | None = None) -> dict[str, Any]:
    standings: dict[str, dict[str, TeamStanding]] = {}
    for fixture in repository.list_fixtures():
        group = _group_label(str(fixture.get("stage") or ""))
        if not group:
            continue
        group_table = standings.setdefault(group, {})
        home = group_table.setdefault(
            fixture["home_team_id"],
            TeamStanding(fixture["home_team_id"], fixture["home_team"], group),
        )
        away = group_table.setdefault(
            fixture["away_team_id"],
            TeamStanding(fixture["away_team_id"], fixture["away_team"], group),
        )
        score = fixture.get("score") or {}
        home_score = score.get("home")
        away_score = score.get("away")
        if home_score is not None and away_score is not None:
            _apply_actual(home, away, int(home_score), int(away_score))
            continue
        prediction = predict_match(
            fixture["id"],
            repository.get_team_features(fixture["home_team_id"]),
            repository.get_team_features(fixture["away_team_id"]),
            learned_model=learned_model,
        )
        _apply_expected(home, away, prediction)

    ranked_groups: list[tuple[str, list[TeamStanding]]] = []
    third_place: list[TeamStanding] = []
    for group, table in sorted(standings.items()):
        ranked = sorted(table.values(), key=_sort_key, reverse=True)
        ranked_groups.append((group, ranked))
        if len(ranked) >= 3:
            third_place.append(ranked[2])
    best_thirds = {team.team_id for team in sorted(third_place, key=_sort_key, reverse=True)[:8]}

    group_payload = []
    qualifiers: list[tuple[int, TeamStanding]] = []
    for group, ranked in ranked_groups:
        rows = []
        for index, team in enumerate(ranked, start=1):
            qualification = "qualified" if index <= 2 else "best-third" if index == 3 and team.team_id in best_thirds else "out"
            if qualification != "out":
                qualifiers.append((index, team))
            rows.append(_standing_payload(team, index, qualification))
        group_payload.append({"group": group, "teams": rows})

    seeded = sorted(qualifiers, key=lambda item: (item[0], -item[1].points, -item[1].goal_difference, -item[1].goals_for, item[1].team_name))
    bracket_teams = [
        BracketTeam(team.team_id, team.team_name, f"{team.group.replace('Group ', '')}{rank}")
        for rank, team in seeded[:32]
    ]
    paired: list[BracketTeam] = []
    left = 0
    right = len(bracket_teams) - 1
    while left < right:
        paired.extend([bracket_teams[left], bracket_teams[right]])
        left += 1
        right -= 1

    bracket = []
    teams = paired
    for round_name in ("Round of 32", "Round of 16", "Quarterfinals", "Semifinals", "Final"):
        round_payload, teams = _play_round(round_name, teams, repository, learned_model)
        bracket.append(round_payload)

    champion = teams[0] if teams else BracketTeam("", "", "")
    return {
        "model_version": MODEL_VERSION,
        "group_rankings": group_payload,
        "qualifiers_count": len(bracket_teams),
        "bracket": bracket,
        "champion": {
            "team_id": champion.team_id,
            "team_name": champion.team_name,
            "title_probability": _round(champion.path_probability),
        },
        "notes": [
            "Group rankings combine actual scores when present with model expected points for unplayed fixtures.",
            "Knockout bracket is a deterministic projection from current group rankings, not an official FIFA slot confirmation.",
        ],
    }
