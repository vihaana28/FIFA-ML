from __future__ import annotations


def dixon_coles_tau(home_score: int, away_score: int, home_goals: float, away_goals: float, rho: float) -> float:
    if home_score == 0 and away_score == 0:
        return 1 - (home_goals * away_goals * rho)
    if home_score == 0 and away_score == 1:
        return 1 + (home_goals * rho)
    if home_score == 1 and away_score == 0:
        return 1 + (away_goals * rho)
    if home_score == 1 and away_score == 1:
        return 1 - rho
    return 1.0


def apply_dixon_coles(matrix: list[dict], home_goals: float, away_goals: float, rho: float = -0.08) -> list[dict]:
    adjusted = []
    for cell in matrix:
        probability = float(cell["probability"])
        if cell.get("score") != "other":
            probability *= max(
                0.01,
                dixon_coles_tau(
                    int(cell["home_goals"]),
                    int(cell["away_goals"]),
                    home_goals,
                    away_goals,
                    rho,
                ),
            )
        adjusted.append({**cell, "probability": probability})
    total = sum(float(cell["probability"]) for cell in adjusted) or 1.0
    return [{**cell, "probability": float(cell["probability"]) / total} for cell in adjusted]


def wdl_from_matrix(matrix: list[dict]) -> dict[str, float]:
    outcomes = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for cell in matrix:
        if cell.get("score") == "other":
            continue
        home_goals = int(cell["home_goals"])
        away_goals = int(cell["away_goals"])
        probability = float(cell["probability"])
        if home_goals > away_goals:
            outcomes["home"] += probability
        elif home_goals == away_goals:
            outcomes["draw"] += probability
        else:
            outcomes["away"] += probability
    total = sum(outcomes.values()) or 1.0
    return {key: value / total for key, value in outcomes.items()}
