from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from math import log
from pathlib import Path
from typing import Any, Iterable

from app.data import TEAM_PRIORS
from app.dixon_coles import apply_dixon_coles, wdl_from_matrix
from app.providers import slugify


LEARNED_MODEL_VERSION = "learned-poisson-dixon-coles-v1"
DEFAULT_LEARNED_MODEL_PATH = Path("data/model/learned_goal_model.joblib")
RHO_CANDIDATES = (-0.16, -0.12, -0.08, -0.04, 0.0, 0.04)
FEATURE_NAMES = [
    "home_attack",
    "home_defense",
    "home_elo_scaled",
    "home_recent_form",
    "home_player_strength",
    "away_attack",
    "away_defense",
    "away_elo_scaled",
    "away_recent_form",
    "away_player_strength",
    "home_matches",
    "away_matches",
    "home_gf_avg",
    "home_ga_avg",
    "away_gf_avg",
    "away_ga_avg",
    "home_points_rate",
    "away_points_rate",
    "neutral",
    "is_world_cup",
    "is_friendly",
]


@dataclass(frozen=True)
class TrainingMatch:
    match_date: date
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    tournament: str = ""
    neutral: bool = False
    source: str = "unknown"


@dataclass(frozen=True)
class TrainingExample:
    match: TrainingMatch
    features: dict[str, float]


@dataclass
class _RollingTeam:
    matches: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    def features(self) -> dict[str, float]:
        if not self.matches:
            return {"matches": 0.0, "gf_avg": 1.20, "ga_avg": 1.20, "points_rate": 0.50}
        return {
            "matches": float(min(self.matches, 50)),
            "gf_avg": self.goals_for / self.matches,
            "ga_avg": self.goals_against / self.matches,
            "points_rate": self.points / (self.matches * 3),
        }

    def apply(self, goals_for: int, goals_against: int) -> None:
        self.matches += 1
        self.goals_for += goals_for
        self.goals_against += goals_against
        if goals_for > goals_against:
            self.points += 3
        elif goals_for == goals_against:
            self.points += 1


@dataclass
class LearnedGoalModel:
    home_model: Any
    away_model: Any
    feature_names: list[str]
    rho: float
    metrics: dict[str, Any] = field(default_factory=dict)
    source_manifest: list[dict[str, Any]] = field(default_factory=list)

    def predict_expected_goals(self, home: Any, away: Any) -> tuple[float, float]:
        features = feature_vector_for_fixture(home, away)
        matrix = [[features[name] for name in self.feature_names]]
        home_goals = float(self.home_model.predict(matrix)[0])
        away_goals = float(self.away_model.predict(matrix)[0])
        return _clamp(home_goals, 0.15, 4.5), _clamp(away_goals, 0.15, 4.5)


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "neutral"}


def _prior_for(team_name: str) -> dict[str, float]:
    slug = slugify(team_name)
    aliases = {
        "united-states": "usa",
        "usa": "usa",
        "czechia": "czech-republic",
        "korea-republic": "south-korea",
        "republic-of-korea": "south-korea",
        "turkiye": "turkey",
        "cote-d-ivoire": "ivory-coast",
        "cape-verde-islands": "cape-verde",
        "congo-dr": "dr-congo",
    }
    return TEAM_PRIORS.get(aliases.get(slug, slug), {"attack": 1.0, "defense": 1.05, "elo": 1650, "recent_form": 0.48, "player_strength": 0.48})


def parse_international_results_training_matches(rows: Iterable[dict[str, Any]]) -> list[TrainingMatch]:
    matches: list[TrainingMatch] = []
    for row in rows:
        match_date = _parse_date(row.get("date"))
        home_score = _to_int(row.get("home_score"))
        away_score = _to_int(row.get("away_score"))
        home_team = str(row.get("home_team") or "").strip()
        away_team = str(row.get("away_team") or "").strip()
        if not match_date or home_score is None or away_score is None or not home_team or not away_team:
            continue
        matches.append(
            TrainingMatch(
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                tournament=str(row.get("tournament") or ""),
                neutral=_to_bool(row.get("neutral")),
                source="martj42/international_results",
            )
        )
    return matches


def parse_openfootball_training_matches(payload: dict[str, Any]) -> list[TrainingMatch]:
    matches: list[TrainingMatch] = []
    for item in payload.get("matches", []):
        match_date = _parse_date(item.get("date"))
        home_team = str(item.get("team1") or item.get("home_team") or "").strip()
        away_team = str(item.get("team2") or item.get("away_team") or "").strip()
        home_score = _to_int(item.get("score1") if "score1" in item else item.get("home_score"))
        away_score = _to_int(item.get("score2") if "score2" in item else item.get("away_score"))
        if not match_date or not home_team or not away_team or home_score is None or away_score is None:
            continue
        matches.append(
            TrainingMatch(
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                tournament=str(item.get("round") or item.get("stage") or "FIFA World Cup"),
                neutral=True,
                source="openfootball/worldcup",
            )
        )
    return matches


def parse_football_data_training_matches(payload: dict[str, Any]) -> list[TrainingMatch]:
    matches: list[TrainingMatch] = []
    for item in payload.get("matches", []):
        if item.get("status") != "FINISHED":
            continue
        full_time = (item.get("score") or {}).get("fullTime") or {}
        home_score = _to_int(full_time.get("home"))
        away_score = _to_int(full_time.get("away"))
        match_date = _parse_date(item.get("utcDate"))
        home_team = str((item.get("homeTeam") or {}).get("name") or "").strip()
        away_team = str((item.get("awayTeam") or {}).get("name") or "").strip()
        if not match_date or not home_team or not away_team or home_score is None or away_score is None:
            continue
        matches.append(
            TrainingMatch(
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                home_score=home_score,
                away_score=away_score,
                tournament=str((item.get("competition") or {}).get("name") or item.get("stage") or ""),
                neutral=True,
                source="football-data.org",
            )
        )
    return matches


def _match_flags(match: TrainingMatch) -> dict[str, float]:
    tournament = match.tournament.lower()
    return {
        "neutral": 1.0 if match.neutral else 0.0,
        "is_world_cup": 1.0 if "world cup" in tournament else 0.0,
        "is_friendly": 1.0 if tournament == "friendly" else 0.0,
    }


def _example_features(match: TrainingMatch, home_roll: dict[str, float], away_roll: dict[str, float]) -> dict[str, float]:
    home_prior = _prior_for(match.home_team)
    away_prior = _prior_for(match.away_team)
    return {
        "home_attack": float(home_prior["attack"]),
        "home_defense": float(home_prior["defense"]),
        "home_elo_scaled": float(home_prior["elo"]) / 1800,
        "home_recent_form": float(home_prior["recent_form"]),
        "home_player_strength": float(home_prior["player_strength"]),
        "away_attack": float(away_prior["attack"]),
        "away_defense": float(away_prior["defense"]),
        "away_elo_scaled": float(away_prior["elo"]) / 1800,
        "away_recent_form": float(away_prior["recent_form"]),
        "away_player_strength": float(away_prior["player_strength"]),
        "home_matches": home_roll["matches"],
        "away_matches": away_roll["matches"],
        "home_gf_avg": home_roll["gf_avg"],
        "home_ga_avg": home_roll["ga_avg"],
        "away_gf_avg": away_roll["gf_avg"],
        "away_ga_avg": away_roll["ga_avg"],
        "home_points_rate": home_roll["points_rate"],
        "away_points_rate": away_roll["points_rate"],
        **_match_flags(match),
    }


def build_training_examples(matches: Iterable[TrainingMatch]) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    states: dict[str, _RollingTeam] = {}
    for match in sorted(matches, key=lambda item: (item.match_date, item.home_team, item.away_team)):
        home_id = slugify(match.home_team)
        away_id = slugify(match.away_team)
        home_state = states.setdefault(home_id, _RollingTeam())
        away_state = states.setdefault(away_id, _RollingTeam())
        examples.append(TrainingExample(match=match, features=_example_features(match, home_state.features(), away_state.features())))
        home_state.apply(match.home_score, match.away_score)
        away_state.apply(match.away_score, match.home_score)
    return examples


def feature_vector_for_fixture(home: Any, away: Any) -> dict[str, float]:
    return {
        "home_attack": float(home.attack),
        "home_defense": float(home.defense),
        "home_elo_scaled": float(home.elo) / 1800,
        "home_recent_form": float(home.recent_form),
        "home_player_strength": float(home.player_strength),
        "away_attack": float(away.attack),
        "away_defense": float(away.defense),
        "away_elo_scaled": float(away.elo) / 1800,
        "away_recent_form": float(away.recent_form),
        "away_player_strength": float(away.player_strength),
        "home_matches": 20.0,
        "away_matches": 20.0,
        "home_gf_avg": max(0.1, float(home.attack) * 1.35),
        "home_ga_avg": max(0.1, float(home.defense) * 1.10),
        "away_gf_avg": max(0.1, float(away.attack) * 1.10),
        "away_ga_avg": max(0.1, float(away.defense) * 1.20),
        "home_points_rate": float(home.recent_form),
        "away_points_rate": float(away.recent_form),
        "neutral": 1.0,
        "is_world_cup": 1.0,
        "is_friendly": 0.0,
    }


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _matrix(home_goals: float, away_goals: float, rho: float) -> list[dict[str, Any]]:
    from app.model import score_matrix

    return apply_dixon_coles(score_matrix(home_goals, away_goals), home_goals, away_goals, rho=rho)


def _actual_outcome(match: TrainingMatch) -> str:
    if match.home_score > match.away_score:
        return "home"
    if match.home_score < match.away_score:
        return "away"
    return "draw"


def _rps(predicted: dict[str, float], actual: str) -> float:
    order = ("home", "draw", "away")
    pred_cdf = 0.0
    actual_cdf = 0.0
    score = 0.0
    for key in order[:-1]:
        pred_cdf += predicted[key]
        actual_cdf += 1.0 if key == actual else 0.0
        score += (pred_cdf - actual_cdf) ** 2
    return score / 2


def _brier(predicted: dict[str, float], actual: str) -> float:
    return sum((predicted[key] - (1.0 if key == actual else 0.0)) ** 2 for key in ("home", "draw", "away"))


def _log_loss(matrix: list[dict[str, Any]], match: TrainingMatch) -> float:
    exact = f"{match.home_score}-{match.away_score}"
    probability = next((float(cell["probability"]) for cell in matrix if cell["score"] == exact), 1e-9)
    return -log(max(probability, 1e-9))


def _evaluate_predictions(predictions: list[tuple[TrainingMatch, float, float]], rho: float) -> dict[str, float]:
    rows = []
    for match, home_goals, away_goals in predictions:
        matrix = _matrix(home_goals, away_goals, rho)
        wdl = wdl_from_matrix(matrix)
        actual = _actual_outcome(match)
        rows.append({"brier": _brier(wdl, actual), "rps": _rps(wdl, actual), "log_loss": _log_loss(matrix, match)})
    if not rows:
        return {"brier_score": 0.0, "ranked_probability_score": 0.0, "log_loss": 0.0}
    return {
        "brier_score": sum(row["brier"] for row in rows) / len(rows),
        "ranked_probability_score": sum(row["rps"] for row in rows) / len(rows),
        "log_loss": sum(row["log_loss"] for row in rows) / len(rows),
    }


def _source_manifest(matches: list[TrainingMatch]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for match in matches:
        counts[match.source] = counts.get(match.source, 0) + 1
    return [{"source": source, "matches": count} for source, count in sorted(counts.items())]


def train_learned_goal_model(
    matches: Iterable[TrainingMatch],
    output_path: str | Path = DEFAULT_LEARNED_MODEL_PATH,
    min_examples: int = 40,
) -> dict[str, Any]:
    output = Path(output_path)
    matches = list(matches)
    examples = build_training_examples(matches)
    metadata: dict[str, Any] = {
        "model_type": LEARNED_MODEL_VERSION,
        "training_examples": len(examples),
        "source_manifest": _source_manifest(matches),
        "promoted": False,
    }
    if len(examples) < min_examples:
        metadata["reason"] = "not_enough_training_examples"
        return metadata
    try:
        from joblib import dump
        from sklearn.linear_model import PoissonRegressor
    except ImportError as exc:
        metadata["reason"] = f"missing_dependency:{exc.name}"
        return metadata

    split = max(1, int(len(examples) * 0.80))
    train_examples = examples[:split]
    validation_examples = examples[split:]
    if not validation_examples:
        metadata["reason"] = "not_enough_validation_examples"
        return metadata

    x_train = [[example.features[name] for name in FEATURE_NAMES] for example in train_examples]
    y_home = [example.match.home_score for example in train_examples]
    y_away = [example.match.away_score for example in train_examples]
    home_model = PoissonRegressor(alpha=0.01, max_iter=1000)
    away_model = PoissonRegressor(alpha=0.01, max_iter=1000)
    home_model.fit(x_train, y_home)
    away_model.fit(x_train, y_away)

    x_validation = [[example.features[name] for name in FEATURE_NAMES] for example in validation_examples]
    learned_predictions = [
        (example.match, _clamp(float(home), 0.15, 4.5), _clamp(float(away), 0.15, 4.5))
        for example, home, away in zip(validation_examples, home_model.predict(x_validation), away_model.predict(x_validation))
    ]
    baseline_predictions = [
        (
            example.match,
            _clamp(1.35 * example.features["home_attack"] * example.features["away_defense"], 0.15, 4.5),
            _clamp(1.08 * example.features["away_attack"] * example.features["home_defense"], 0.15, 4.5),
        )
        for example in validation_examples
    ]
    best = min(
        ((_evaluate_predictions(learned_predictions, rho), rho) for rho in RHO_CANDIDATES),
        key=lambda item: (item[0]["ranked_probability_score"], item[0]["brier_score"], item[0]["log_loss"]),
    )
    learned_metrics, rho = best
    baseline_metrics = _evaluate_predictions(baseline_predictions, -0.08)
    promoted = (
        (
            learned_metrics["brier_score"] <= baseline_metrics["brier_score"] * 0.98
            or learned_metrics["ranked_probability_score"] <= baseline_metrics["ranked_probability_score"] * 0.98
        )
        and learned_metrics["log_loss"] <= baseline_metrics["log_loss"] * 1.02
    )
    metadata.update(
        {
            "validation_examples": len(validation_examples),
            "rho": rho,
            "metrics": {"learned": learned_metrics, "baseline": baseline_metrics},
            "promoted": promoted,
        }
    )
    if not promoted:
        metadata["reason"] = "validation_gate_not_met"
        return metadata

    output.parent.mkdir(parents=True, exist_ok=True)
    dump(
        {
            "model_type": LEARNED_MODEL_VERSION,
            "home_model": home_model,
            "away_model": away_model,
            "feature_names": FEATURE_NAMES,
            "rho": rho,
            "metrics": metadata["metrics"],
            "source_manifest": metadata["source_manifest"],
        },
        output,
    )
    metadata["artifact_path"] = str(output)
    return metadata


def load_learned_goal_model(path: str | Path = DEFAULT_LEARNED_MODEL_PATH) -> LearnedGoalModel | None:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return None
    try:
        from joblib import load

        payload = load(artifact_path)
    except Exception:
        return None
    return learned_goal_model_from_payload(payload)


def load_learned_goal_model_bytes(payload_bytes: bytes) -> LearnedGoalModel | None:
    try:
        from joblib import load

        payload = load(BytesIO(payload_bytes))
    except Exception:
        return None
    return learned_goal_model_from_payload(payload)


def learned_goal_model_from_payload(payload: dict[str, Any]) -> LearnedGoalModel | None:
    if payload.get("model_type") != LEARNED_MODEL_VERSION:
        return None
    return LearnedGoalModel(
        home_model=payload["home_model"],
        away_model=payload["away_model"],
        feature_names=list(payload.get("feature_names") or FEATURE_NAMES),
        rho=float(payload.get("rho", -0.08)),
        metrics=dict(payload.get("metrics") or {}),
        source_manifest=list(payload.get("source_manifest") or []),
    )
