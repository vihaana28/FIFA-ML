from __future__ import annotations

from dataclasses import asdict, dataclass
from math import exp, factorial
from typing import Any

from app.dixon_coles import apply_dixon_coles, wdl_from_matrix
from app.learned_model import LEARNED_MODEL_VERSION


MODEL_VERSION = LEARNED_MODEL_VERSION
HEURISTIC_MODEL_VERSION = "dixon-coles-poisson-v2"
DIXON_COLES_RHO = -0.08
HOME_ADVANTAGE = 1.08
DRAW_ADJUSTMENT = 1.0
TIME_DECAY = 0.0065


@dataclass(frozen=True)
class TeamFeatures:
    team_id: str
    team_name: str
    attack: float
    defense: float
    elo: float
    recent_form: float
    player_strength: float


def _poisson(goal_count: int, expected_goals: float) -> float:
    return (expected_goals**goal_count) * exp(-expected_goals) / factorial(goal_count)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def expected_goals(home: TeamFeatures, away: TeamFeatures) -> tuple[float, float]:
    elo_adjustment = (home.elo - away.elo) / 900
    form_adjustment = (home.recent_form - away.recent_form) * 0.28
    player_adjustment = (home.player_strength - away.player_strength) * 0.22

    home_goals = 1.35 * home.attack * away.defense
    away_goals = 1.08 * away.attack * home.defense

    home_goals += elo_adjustment + form_adjustment + player_adjustment
    away_goals -= (elo_adjustment * 0.72) + (form_adjustment * 0.55) + (player_adjustment * 0.55)

    return _clamp(home_goals, 0.15, 4.5), _clamp(away_goals, 0.15, 4.5)


def score_matrix(home_goals: float, away_goals: float, max_goals: int = 5) -> list[dict[str, float | int | str]]:
    cells: list[dict[str, float | int | str]] = []
    finite_probability = 0.0

    for home_score in range(max_goals + 1):
        for away_score in range(max_goals + 1):
            probability = _poisson(home_score, home_goals) * _poisson(away_score, away_goals)
            finite_probability += probability
            cells.append(
                {
                    "score": f"{home_score}-{away_score}",
                    "home_goals": home_score,
                    "away_goals": away_score,
                    "probability": probability,
                }
            )

    cells.append({"score": "other", "home_goals": None, "away_goals": None, "probability": max(0, 1 - finite_probability)})
    total = sum(float(cell["probability"]) for cell in cells)
    return [{**cell, "probability": float(cell["probability"]) / total} for cell in cells]


def top_scorelines(matrix: list[dict[str, float | int | str]], limit: int = 5) -> list[dict[str, float | str]]:
    candidates = [cell for cell in matrix if cell["score"] != "other"]
    ranked = sorted(candidates, key=lambda cell: float(cell["probability"]), reverse=True)
    return [{"score": str(cell["score"]), "probability": float(cell["probability"])} for cell in ranked[:limit]]


def _data_quality(home: TeamFeatures, away: TeamFeatures, confidence_score: float) -> dict:
    missing = []
    if min(home.player_strength, away.player_strength) < 0.55:
        missing.append("player_availability")
    if min(home.recent_form, away.recent_form) < 0.45:
        missing.append("recent_form")
    if min(home.elo, away.elo) <= 0:
        missing.append("elo")

    level = "high" if confidence_score >= 0.68 and not missing else "medium" if confidence_score >= 0.45 else "low"
    if len(missing) >= 2:
        level = "low"
    return {
        "level": level,
        "score": round(confidence_score, 4),
        "missing": missing,
        "sources": ["current-results", "recent-form", "elo-priors", "player-availability-optional"],
    }


def predict_match(fixture_id: str, home: TeamFeatures, away: TeamFeatures, learned_model: Any | None = None) -> dict:
    model_version = HEURISTIC_MODEL_VERSION
    rho = DIXON_COLES_RHO
    if learned_model is not None:
        home_xg, away_xg = learned_model.predict_expected_goals(home, away)
        model_version = LEARNED_MODEL_VERSION
        rho = float(getattr(learned_model, "rho", DIXON_COLES_RHO))
    else:
        home_xg, away_xg = expected_goals(home, away)
    raw_matrix = score_matrix(home_xg, away_xg)
    adjusted_matrix = apply_dixon_coles(raw_matrix, home_xg, away_xg, rho=rho)
    wdl = wdl_from_matrix(adjusted_matrix)
    confidence_score = (home.recent_form + away.recent_form + home.player_strength + away.player_strength) / 4
    confidence = "high" if confidence_score >= 0.68 else "medium" if confidence_score >= 0.45 else "low"
    data_quality = _data_quality(home, away, confidence_score)
    risk_flags = []
    if data_quality["level"] == "low":
        risk_flags.append("Low data quality")
    if "player_availability" in data_quality["missing"]:
        risk_flags.append("Missing player availability")

    return {
        "fixture_id": fixture_id,
        "model_type": model_version,
        "model_version": model_version,
        "expected_goals": {"home": home_xg, "away": away_xg},
        "wdl": wdl,
        "calibrated_wdl": wdl,
        "top_scores": top_scorelines(adjusted_matrix),
        "score_matrix": adjusted_matrix,
        "raw_score_matrix": raw_matrix,
        "adjusted_score_matrix": adjusted_matrix,
        "confidence": confidence,
        "data_quality": data_quality,
        "calibration": {"method": "validation" if learned_model is not None else "none", "market_weight": 0.0, "wdl": wdl},
        "risk_flags": risk_flags,
        "features": {"home": asdict(home), "away": asdict(away)},
        "explanation": [
            "Expected goals combine attack form, opponent defense, Elo gap, recent form, and player availability.",
            "Learned Poisson goal rates are used when a validated free-data artifact is available; otherwise the v2 heuristic is used.",
            "Dixon-Coles correction adjusts low-score football outcomes before scoreline ranking.",
            "Player stats are best-effort: squad aggregate first, club-form enrichment only when free APIs expose enough data.",
            "Betting outputs are strategy simulations, not guarantees or real-money execution.",
        ],
    }
