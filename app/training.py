from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.data import TEAM_PRIORS
from app.db import Repository
from app.learned_model import (
    DEFAULT_LEARNED_MODEL_PATH,
    LEARNED_MODEL_VERSION,
    TrainingMatch,
    parse_international_results_training_matches,
    train_learned_goal_model,
)
from app.model import DIXON_COLES_RHO, DRAW_ADJUSTMENT, HOME_ADVANTAGE, MODEL_VERSION, TIME_DECAY
from app.recent_form import load_recent_results_rows
from app.recent_form import COMPETITIVE_WEIGHT, CURRENT_WORLD_CUP_WEIGHT, FRIENDLY_WEIGHT, OLD_MATCH_MULTIPLIER


DEFAULT_MODEL_ARTIFACT_PATH = Path("data/model/model.json")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fixture_training_matches(repository: Repository) -> list[TrainingMatch]:
    matches = []
    for fixture in repository.list_fixtures():
        score = fixture.get("score") or {}
        home_score = score.get("home")
        away_score = score.get("away")
        if fixture.get("status") != "FINISHED" or home_score is None or away_score is None:
            continue
        try:
            match_date = datetime.fromisoformat(str(fixture["kickoff"]).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        matches.append(
            TrainingMatch(
                match_date=match_date,
                home_team=fixture["home_team"],
                away_team=fixture["away_team"],
                home_score=int(home_score),
                away_score=int(away_score),
                tournament=fixture.get("stage", "FIFA World Cup"),
                neutral=True,
                source=f"{fixture.get('provider') or 'fixture'} finished results",
            )
        )
    return matches


def collect_free_training_matches(repository: Repository) -> list[TrainingMatch]:
    matches = repository.list_training_matches()
    rows = load_recent_results_rows()
    if rows:
        matches.extend(parse_international_results_training_matches(rows))
    matches.extend(_fixture_training_matches(repository))
    unique: dict[tuple[str, str, str, str], TrainingMatch] = {}
    for match in matches:
        unique[(match.source, match.match_date.isoformat(), match.home_team, match.away_team)] = match
    return sorted(unique.values(), key=lambda item: (item.match_date, item.home_team, item.away_team))


def build_model_artifact(
    repository: Repository,
    generated_at: str | None = None,
    learned_model_metadata: dict | None = None,
) -> dict:
    teams = {}
    seen = {}
    for fixture in repository.list_fixtures():
        seen[fixture["home_team_id"]] = fixture["home_team"]
        seen[fixture["away_team_id"]] = fixture["away_team"]
    if not seen:
        seen = {team_id: team_id.replace("-", " ").title() for team_id in TEAM_PRIORS}
    for team_id, team_name in sorted(seen.items(), key=lambda item: item[1]):
        try:
            features = repository.get_team_features(team_id)
        except KeyError:
            features = repository._feature_for_team(team_id, team_name)
        teams[team_id] = asdict(features)
    return {
        "model_type": MODEL_VERSION,
        "generated_at": generated_at or _utc_iso(),
        "team_count": len(teams),
        "teams": teams,
        "data_sources": [
            "martj42/international_results when configured through INTERNATIONAL_RESULTS_CSV",
            "openfootball/worldcup public-domain fixtures/results",
            "football-data.org 2026 World Cup results",
            "International results CSV including friendlies when configured",
            "StatsBomb Open Data historical World Cup event stats",
            "Hand-tuned priors for fallback strength",
        ],
        "learned_model": learned_model_metadata
        or {
            "model_type": LEARNED_MODEL_VERSION,
            "promoted": False,
            "reason": "training_not_run",
            "artifact_path": str(DEFAULT_LEARNED_MODEL_PATH),
        },
        "feature_weights": {
            "current_world_cup": CURRENT_WORLD_CUP_WEIGHT,
            "competitive": COMPETITIVE_WEIGHT,
            "friendly": FRIENDLY_WEIGHT,
            "old_match_multiplier": OLD_MATCH_MULTIPLIER,
            "rho": DIXON_COLES_RHO,
            "home_advantage": HOME_ADVANTAGE,
            "draw_adjustment": DRAW_ADJUSTMENT,
            "time_decay": TIME_DECAY,
        },
        "note": "Artifact/debug output. Runtime predictions use DB feature profiles with current results and recent form before priors.",
    }


def write_model_artifact(repository: Repository, path: str | Path = DEFAULT_MODEL_ARTIFACT_PATH) -> dict:
    output_path = Path(path)
    learned_path = output_path.parent / DEFAULT_LEARNED_MODEL_PATH.name
    training_matches = collect_free_training_matches(repository)
    learned_metadata = train_learned_goal_model(training_matches, learned_path)
    artifact = build_model_artifact(repository, learned_model_metadata=learned_metadata)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def read_model_artifact(path: str | Path = DEFAULT_MODEL_ARTIFACT_PATH) -> dict:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {}
    return json.loads(artifact_path.read_text(encoding="utf-8"))
