from __future__ import annotations

import json
import math
from pathlib import Path

from app.model import predict_match


def _brier(predicted: dict[str, float], actual: str) -> float:
    return sum((predicted[key] - (1.0 if key == actual else 0.0)) ** 2 for key in ("home", "draw", "away"))


def _ranked_probability_score(predicted: dict[str, float], actual: str) -> float:
    order = ("home", "draw", "away")
    actual_vector = [1.0 if key == actual else 0.0 for key in order]
    pred_cdf = 0.0
    actual_cdf = 0.0
    score = 0.0
    for idx in range(len(order) - 1):
        pred_cdf += predicted[order[idx]]
        actual_cdf += actual_vector[idx]
        score += (pred_cdf - actual_cdf) ** 2
    return score / (len(order) - 1)


def build_backtest_metrics(repository) -> dict:
    rows = []
    for fixture in repository.list_fixtures():
        score = fixture.get("score") or {}
        if fixture.get("status") != "FINISHED" or score.get("home") is None or score.get("away") is None:
            continue
        home = repository.get_team_features(fixture["home_team_id"])
        away = repository.get_team_features(fixture["away_team_id"])
        prediction = predict_match(fixture["id"], home, away)
        actual = "home" if score["home"] > score["away"] else "away" if score["home"] < score["away"] else "draw"
        exact = f"{score['home']}-{score['away']}"
        exact_probability = next(
            (cell["probability"] for cell in prediction["adjusted_score_matrix"] if cell["score"] == exact),
            1e-9,
        )
        rows.append(
            {
                "brier": _brier(prediction["wdl"], actual),
                "rps": _ranked_probability_score(prediction["wdl"], actual),
                "log_loss": -math.log(max(float(exact_probability), 1e-9)),
                "confidence": prediction["confidence"],
            }
        )
    if not rows:
        return {
            "sample_matches": 0,
            "brier_score": None,
            "log_loss": None,
            "ranked_probability_score": None,
            "calibration_buckets": [],
        }
    return {
        "sample_matches": len(rows),
        "brier_score": sum(row["brier"] for row in rows) / len(rows),
        "log_loss": sum(row["log_loss"] for row in rows) / len(rows),
        "ranked_probability_score": sum(row["rps"] for row in rows) / len(rows),
        "calibration_buckets": [{"bucket": "all", "matches": len(rows)}],
    }


def write_backtest_metrics(repository, path: str | Path) -> dict:
    metrics = build_backtest_metrics(repository)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def read_backtest_metrics(path: str | Path) -> dict:
    metrics_path = Path(path)
    if not metrics_path.exists():
        return {
            "sample_matches": 0,
            "brier_score": None,
            "log_loss": None,
            "ranked_probability_score": None,
            "calibration_buckets": [],
        }
    return json.loads(metrics_path.read_text(encoding="utf-8"))
