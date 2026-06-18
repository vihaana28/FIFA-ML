from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.backtesting import read_backtest_metrics, write_backtest_metrics
from app.betting import expected_value, implied_probability, kelly_fraction, parlay_outcome, remove_vig
from app.calibration import calibration_payload
from app.data import DATA_SOURCES
from app.db import Repository
from app.learned_model import DEFAULT_LEARNED_MODEL_PATH, load_learned_goal_model, load_learned_goal_model_bytes
from app.model import MODEL_VERSION, predict_match
from app.providers import ApiFootballClient, FootballDataClient, OpenFootballClient, TheOddsApiClient
from app.recommendations import moneyline_market, recommend_bets
from app.settings import load_env_file
from app.stats_sources import StatsBombOpenDataClient
from app.sync_service import SyncService, run_auto_sync_loop
from app.training import DEFAULT_MODEL_ARTIFACT_PATH, read_model_artifact, write_model_artifact
from app.tournament_projection import build_tournament_projection


class ParlayLeg(BaseModel):
    fixture_id: str
    market: str
    selection: str
    probability: float = Field(ge=0, le=1)
    american_odds: int


class ParlayRequest(BaseModel):
    stake: float = Field(gt=0)
    legs: list[ParlayLeg] = Field(min_length=1)


class StatProfileIngestRequest(BaseModel):
    team_profiles: list[dict] = Field(default_factory=list)
    player_profiles: list[dict] = Field(default_factory=list)


def create_app(
    database_url: str | None = None,
    model_artifact_path: str | Path = DEFAULT_MODEL_ARTIFACT_PATH,
    backtest_artifact_path: str | Path | None = None,
) -> FastAPI:
    load_env_file()
    database_url = database_url or os.environ.get("DATABASE_URL", "data/fifa_ml.sqlite3")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task: asyncio.Task | None = None
        if app.state.sync_service.config.enabled and not os.environ.get("VERCEL"):
            task = asyncio.create_task(run_auto_sync_loop(app.state.sync_service))
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="FIFA ML Predictor", version="0.1.0", lifespan=lifespan)
    app.state.repository = Repository(database_url)
    app.state.api_football = ApiFootballClient()
    app.state.football_data = FootballDataClient()
    app.state.the_odds_api = TheOddsApiClient()
    app.state.openfootball = OpenFootballClient()
    app.state.statsbomb = StatsBombOpenDataClient()
    app.state.model_artifact_path = Path(model_artifact_path)
    app.state.learned_model_path = app.state.model_artifact_path.parent / DEFAULT_LEARNED_MODEL_PATH.name
    app.state.learned_model = _load_learned_model(app.state.repository, app.state.learned_model_path)
    app.state.backtest_artifact_path = Path(backtest_artifact_path) if backtest_artifact_path else app.state.model_artifact_path.parent / "backtest.json"
    app.state.sync_service = SyncService(
        repository=app.state.repository,
        api_football_client=app.state.api_football,
        football_data_client=app.state.football_data,
        odds_client=app.state.the_odds_api,
        openfootball_client=app.state.openfootball,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_repository() -> Repository:
        return app.state.repository

    def require_cron_auth(authorization: str | None = Header(default=None)) -> None:
        secret = os.environ.get("CRON_SECRET")
        if not secret:
            raise HTTPException(status_code=503, detail="CRON_SECRET is not configured")
        if authorization != f"Bearer {secret}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/fixtures")
    def fixtures(repository: Repository = Depends(get_repository)) -> list[dict]:
        return repository.list_fixtures()

    @app.get("/fixtures/{fixture_id}")
    def fixture(fixture_id: str, repository: Repository = Depends(get_repository)) -> dict:
        match = repository.get_fixture(fixture_id)
        if not match:
            raise HTTPException(status_code=404, detail="Fixture not found")
        match["odds"] = repository.get_odds(fixture_id)
        match["home_player_features"] = repository.get_player_features(match["home_team_id"])
        match["away_player_features"] = repository.get_player_features(match["away_team_id"])
        match["home_team_stats"] = repository.get_team_stats(match["home_team_id"])
        match["away_team_stats"] = repository.get_team_stats(match["away_team_id"])
        return match

    @app.get("/predictions/{fixture_id}")
    def prediction(fixture_id: str, repository: Repository = Depends(get_repository)) -> dict:
        match = repository.get_fixture(fixture_id)
        if not match:
            raise HTTPException(status_code=404, detail="Fixture not found")
        home = repository.get_team_features(match["home_team_id"])
        away = repository.get_team_features(match["away_team_id"])
        payload = predict_match(fixture_id, home, away, learned_model=app.state.learned_model)
        odds = repository.get_odds(fixture_id)
        market = moneyline_market(odds)
        if set(market) == {"home", "draw", "away"}:
            fair_market = remove_vig(market)
            payload["odds"] = odds
            payload["market_probabilities"] = fair_market
            payload["calibration"] = {"method": "market-validation", "market_weight": 0.0, "wdl": payload["wdl"]}
            payload["calibrated_wdl"] = payload["wdl"]
            payload["edges"] = {
                outcome: {
                    "model_probability": payload["wdl"][outcome],
                    "market_probability": fair_market[outcome],
                    "edge": payload["wdl"][outcome] - fair_market[outcome],
                    "expected_value_per_10": expected_value(payload["wdl"][outcome], market[outcome], stake=10),
                    "implied_probability": implied_probability(market[outcome]),
                    "american_odds": market[outcome],
                }
                for outcome in ("home", "draw", "away")
            }
            if any(abs(payload["wdl"][outcome] - fair_market[outcome]) >= 0.12 for outcome in ("home", "draw", "away")):
                payload["risk_flags"] = [*payload.get("risk_flags", []), "Market disagrees"]
        repository.save_prediction(fixture_id, payload)
        return payload

    @app.get("/odds/{fixture_id}")
    def odds(fixture_id: str, repository: Repository = Depends(get_repository)) -> dict:
        market = repository.get_odds(fixture_id)
        prices = moneyline_market(market)
        if set(prices) != {"home", "draw", "away"}:
            raise HTTPException(status_code=404, detail="Odds not found")
        return {"fixture_id": fixture_id, "market": market, "fair_probabilities": remove_vig(prices)}

    @app.post("/bets/parlay")
    def parlay(request: ParlayRequest, repository: Repository = Depends(get_repository)) -> dict:
        legs = [leg.model_dump() for leg in request.legs]
        result = parlay_outcome(legs, stake=request.stake)
        payload = {"stake": request.stake, "legs_detail": legs, **result}
        repository.save_bet(payload)
        return payload

    @app.get("/bets/recommendations")
    def recommendations(min_edge: float = 0.03, repository: Repository = Depends(get_repository)) -> dict:
        return recommend_bets(repository, min_edge=min_edge)

    @app.get("/tournament/projection")
    def tournament_projection(repository: Repository = Depends(get_repository)) -> dict:
        return build_tournament_projection(repository, learned_model=app.state.learned_model)

    @app.get("/bets/correct-score/{fixture_id}")
    def correct_score_bets(fixture_id: str, repository: Repository = Depends(get_repository)) -> dict:
        match = repository.get_fixture(fixture_id)
        if not match:
            raise HTTPException(status_code=404, detail="Fixture not found")
        odds = repository.get_odds(fixture_id)
        correct_scores = odds.get("correct_scores") or {}
        if not isinstance(correct_scores, dict) or not correct_scores:
            return {
                "fixture_id": fixture_id,
                "scores": [],
                "reason": "No real correct-score market odds available.",
                "warning": "Strategy simulator only; no guarantee, no bet placement.",
            }
        prediction_payload = predict_match(
            fixture_id,
            repository.get_team_features(match["home_team_id"]),
            repository.get_team_features(match["away_team_id"]),
            learned_model=app.state.learned_model,
        )
        probabilities = {
            str(cell["score"]): float(cell["probability"])
            for cell in prediction_payload["adjusted_score_matrix"]
            if cell.get("score") != "other"
        }
        scores = []
        for score, american_odds in correct_scores.items():
            model_probability = probabilities.get(str(score))
            if model_probability is None:
                continue
            scores.append(
                {
                    "score": str(score),
                    "model_probability": model_probability,
                    "american_odds": american_odds,
                    "implied_probability": implied_probability(american_odds),
                    "expected_value_per_10": expected_value(model_probability, american_odds, stake=10),
                    "kelly_fraction_capped": min(kelly_fraction(model_probability, american_odds), 0.03),
                    "source": odds.get("source", "unknown"),
                }
            )
        scores.sort(key=lambda item: item["expected_value_per_10"], reverse=True)
        return {
            "fixture_id": fixture_id,
            "scores": scores,
            "source": odds.get("source", "unknown"),
            "warning": "Strategy simulator only; no guarantee, no bet placement.",
        }

    @app.get("/bets/parlay-risk")
    def parlay_risk(fixture_id: list[str] = Query(default=[])) -> dict:
        duplicate_fixtures = sorted({item for item in fixture_id if fixture_id.count(item) > 1})
        correlated = bool(duplicate_fixtures)
        return {
            "legs": len(fixture_id),
            "correlated": correlated,
            "risk_level": "high" if correlated else "low",
            "blocked": correlated,
            "blocked_fixture_ids": duplicate_fixtures,
            "flags": ["Same-match correlated legs blocked"] if correlated else [],
            "ev_discount": 0.0 if correlated else 1.0,
        }

    @app.get("/model/metrics")
    def metrics() -> dict:
        backtest = read_backtest_metrics(app.state.backtest_artifact_path)
        if not backtest or backtest.get("sample_matches") == 0:
            persisted = _read_persisted_json_artifact(app.state.repository, "backtest.json")
            if persisted:
                backtest = persisted
        return {
            "model_type": MODEL_VERSION,
            "training_status": "Run POST /admin/train or python scripts/backtest_model.py after adding historical datasets to data/raw.",
            "backtest": backtest,
            **backtest,
            "limitations": [
                "Free API quotas limit live player and club-form depth.",
                "Parlay EV is discounted or blocked when same-match correlation is detected.",
                "No real-money betting execution.",
            ],
        }

    @app.get("/model/artifact")
    def model_artifact(repository: Repository = Depends(get_repository)) -> dict:
        artifact = read_model_artifact(app.state.model_artifact_path)
        if not artifact:
            artifact = _read_persisted_json_artifact(repository, "model.json")
        if not artifact:
            artifact = write_model_artifact(repository, app.state.model_artifact_path)
            repository.save_model_artifact("model.json", artifact, content_type="application/json")
        return {
            "model_type": artifact.get("model_type"),
            "generated_at": artifact.get("generated_at"),
            "team_count": artifact.get("team_count", len(artifact.get("teams", {}))),
            "data_sources": artifact.get("data_sources", []),
            "feature_weights": artifact.get("feature_weights", {}),
            "learned_model": artifact.get("learned_model", {}),
        }

    @app.get("/data/sources")
    def sources() -> list[dict]:
        return DATA_SOURCES

    @app.get("/sync/status")
    def sync_status() -> dict:
        return app.state.sync_service.status()

    @app.get("/stats/teams")
    def team_stats(repository: Repository = Depends(get_repository)) -> list[dict]:
        return repository.list_team_stats()

    @app.get("/stats/players")
    def player_stats(team_id: str | None = None, limit: int = 100, repository: Repository = Depends(get_repository)) -> list[dict]:
        return repository.list_player_stats(team_id=team_id, limit=limit)

    @app.get("/model/features/{team_id}")
    def model_features(team_id: str, repository: Repository = Depends(get_repository)) -> dict:
        try:
            features = repository.get_team_features(team_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Team features not found") from exc
        return {
            "team_id": team_id,
            "features": features.__dict__,
            "player_features": repository.get_player_features(team_id),
            "team_stats": repository.get_team_stats(team_id),
        }

    @app.post("/admin/stats/ingest")
    def ingest_stats(request: StatProfileIngestRequest, repository: Repository = Depends(get_repository)) -> dict:
        repository.save_stat_profiles(request.team_profiles, request.player_profiles)
        return {
            "status": "ingested",
            "team_profiles": len(request.team_profiles),
            "player_profiles": len(request.player_profiles),
        }

    @app.post("/admin/stats/sync")
    def sync_stats(match_limit: int = 32, repository: Repository = Depends(get_repository)) -> dict:
        profiles = app.state.statsbomb.world_cup_profiles(match_limit=match_limit)
        repository.save_stat_profiles(profiles["team_profiles"], profiles["player_profiles"])
        result_profiles = repository.refresh_current_result_stats()
        return {
            "status": "synced",
            "source": "StatsBomb Open Data",
            "team_profiles": len(profiles["team_profiles"]),
            "player_profiles": len(profiles["player_profiles"]),
            "current_result_team_profiles": result_profiles["team_profiles"],
            "match_limit": match_limit,
        }

    @app.post("/admin/sync")
    def sync() -> dict:
        try:
            return app.state.sync_service.sync(force=True, include_odds=True)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc

    @app.post("/admin/cron/sync", dependencies=[Depends(require_cron_auth)])
    def cron_sync(repository: Repository = Depends(get_repository)) -> dict:
        try:
            result = app.state.sync_service.sync(force=True, include_odds=True)
            repository.save_sync_status(result)
            return result
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc

    @app.post("/admin/cron/train", dependencies=[Depends(require_cron_auth)])
    def cron_train(repository: Repository = Depends(get_repository)) -> dict:
        try:
            sync_result = app.state.sync_service.sync(force=True, include_odds=True)
            with tempfile.TemporaryDirectory() as temp_dir:
                model_path = Path(temp_dir) / "model.json"
                backtest_path = Path(temp_dir) / "backtest.json"
                artifact, backtest = _write_and_persist_model_artifacts(repository, model_path, backtest_path)
            app.state.learned_model = _load_learned_model(repository, app.state.learned_model_path)
            return {
                "status": "trained",
                "sync": sync_result,
                "model_type": artifact["model_type"],
                "team_count": artifact["team_count"],
                "learned_model": artifact.get("learned_model", {}),
                "backtest": backtest,
                "message": "Model artifacts persisted for serverless runtime.",
            }
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Training failed: {exc}") from exc

    @app.post("/admin/train")
    def train(repository: Repository = Depends(get_repository)) -> dict:
        artifact, backtest = _write_and_persist_model_artifacts(
            repository,
            app.state.model_artifact_path,
            app.state.backtest_artifact_path,
        )
        app.state.learned_model = _load_learned_model(repository, app.state.learned_model_path)
        return {
            "status": "trained",
            "model_type": artifact["model_type"],
            "team_count": artifact["team_count"],
            "path": str(app.state.model_artifact_path),
            "learned_model_path": str(app.state.learned_model_path),
            "learned_model": artifact.get("learned_model", {}),
            "backtest_path": str(app.state.backtest_artifact_path),
            "backtest": backtest,
            "message": "Model artifact regenerated from free training matches and current DB features.",
        }

    static_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


def _load_learned_model(repository: Repository, path: str | Path):
    saved = repository.get_model_artifact(DEFAULT_LEARNED_MODEL_PATH.name)
    if saved and isinstance(saved.get("payload"), bytes):
        loaded = load_learned_goal_model_bytes(saved["payload"])
        if loaded:
            return loaded
    return load_learned_goal_model(path)


def _read_persisted_json_artifact(repository: Repository, name: str) -> dict[str, Any]:
    saved = repository.get_model_artifact(name)
    if saved and isinstance(saved.get("payload"), dict):
        return saved["payload"]
    return {}


def _write_and_persist_model_artifacts(
    repository: Repository,
    model_artifact_path: str | Path,
    backtest_artifact_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact = write_model_artifact(repository, model_artifact_path)
    repository.save_model_artifact("model.json", artifact, content_type="application/json")

    learned_path = Path(model_artifact_path).parent / DEFAULT_LEARNED_MODEL_PATH.name
    if learned_path.exists():
        repository.save_model_artifact(
            DEFAULT_LEARNED_MODEL_PATH.name,
            learned_path.read_bytes(),
            content_type="application/octet-stream",
            metadata=artifact.get("learned_model", {}),
        )

    backtest = write_backtest_metrics(repository, backtest_artifact_path)
    repository.save_model_artifact("backtest.json", backtest, content_type="application/json")
    return artifact, backtest


app = create_app()
