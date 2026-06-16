from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.db import Repository
from app.providers import ApiFootballClient, FootballDataClient, OpenFootballClient, TheOddsApiClient


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _parse_kickoff(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class AutoSyncConfig:
    enabled: bool = True
    interval_seconds: int = 300
    live_window_hours_before: int = 3
    live_window_hours_after: int = 4

    @classmethod
    def from_env(cls) -> "AutoSyncConfig":
        return cls(
            enabled=_env_bool("AUTO_SYNC_ENABLED", True),
            interval_seconds=max(30, _env_int("AUTO_SYNC_INTERVAL_SECONDS", 300)),
            live_window_hours_before=max(0, _env_int("AUTO_SYNC_LIVE_WINDOW_HOURS_BEFORE", 3)),
            live_window_hours_after=max(0, _env_int("AUTO_SYNC_LIVE_WINDOW_HOURS_AFTER", 4)),
        )


class SyncService:
    def __init__(
        self,
        repository: Repository,
        football_data_client: FootballDataClient | None = None,
        api_football_client: ApiFootballClient | None = None,
        odds_client: TheOddsApiClient | None = None,
        openfootball_client: OpenFootballClient | None = None,
        config: AutoSyncConfig | None = None,
        now: Callable[[], datetime] = _utc_now,
    ):
        self.repository = repository
        self.football_data_client = football_data_client or FootballDataClient()
        self.api_football_client = api_football_client or ApiFootballClient()
        self.odds_client = odds_client or TheOddsApiClient()
        self.openfootball_client = openfootball_client or OpenFootballClient()
        self.config = config or AutoSyncConfig.from_env()
        self.now = now
        self.running = False
        self.last_sync_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None
        self.fixture_source = "cached"
        self.odds_source = "none"
        self.current_result_team_profiles = len(self.repository.list_team_stats())
        self.next_sync_at: datetime | None = None

    def should_poll(self) -> bool:
        now = self.now().astimezone(timezone.utc)
        fixtures = self.repository.list_fixtures()
        if not fixtures:
            return True
        for fixture in fixtures:
            if fixture.get("status") == "FINISHED":
                continue
            kickoff = _parse_kickoff(fixture.get("kickoff", ""))
            if not kickoff:
                continue
            if kickoff.date() == now.date():
                return True
            start = kickoff - timedelta(hours=self.config.live_window_hours_before)
            end = kickoff + timedelta(hours=self.config.live_window_hours_after)
            if start <= now <= end:
                return True
        return False

    def sync(self, force: bool = False, include_odds: bool = False) -> dict:
        now = self.now().astimezone(timezone.utc)
        self.next_sync_at = now + timedelta(seconds=self.config.interval_seconds)
        if not force and not self.should_poll():
            return {**self.status(), "status": "skipped", "changed_fixture_ids": []}
        if self.running:
            return {**self.status(), "status": "already-running", "changed_fixture_ids": []}

        self.running = True
        self.last_sync_at = now
        changed_fixture_ids: list[str] = []
        odds_saved = 0
        try:
            fixtures, fixture_source = self._fetch_fixtures(force=force)
            if fixtures:
                replace_result = self.repository.replace_fixtures(fixtures)
                changed_fixture_ids = replace_result["changed_fixture_ids"]
                self.repository.cache_raw(f"{fixture_source.lower().replace(' ', '-')}-fixtures", fixture_source, {"fixtures": fixtures})
                self.fixture_source = fixture_source
                if changed_fixture_ids:
                    self.repository.delete_predictions(changed_fixture_ids)

            if include_odds:
                odds_saved = self._sync_odds()

            result_profiles = self.repository.refresh_current_result_stats()
            self.current_result_team_profiles = result_profiles["team_profiles"]
            self.last_success_at = now
            self.last_error = None
            self.running = False
            return {
                **self.status(),
                "status": "synced",
                "fixtures": len(self.repository.list_fixtures()),
                "fixture_source": self.fixture_source,
                "odds_saved": odds_saved,
                "odds_source": self.odds_source,
                "current_result_team_profiles": self.current_result_team_profiles,
                "changed_fixture_ids": changed_fixture_ids,
                "message": "Real data synced and cached. Missing odds are shown as no recommendation.",
            }
        except Exception as exc:
            self.last_error = str(exc)
            raise
        finally:
            self.running = False

    def _fetch_fixtures(self, force: bool) -> tuple[list[dict], str]:
        if self.football_data_client.enabled:
            try:
                fixtures = self.football_data_client.world_cup_matches()
                if fixtures:
                    return fixtures, "football-data.org"
            except Exception:
                if not force:
                    raise
        if not force:
            raise RuntimeError("football-data.org token missing or returned no fixtures")
        if self.api_football_client.enabled:
            try:
                fixtures = self.api_football_client.world_cup_fixtures()
                if fixtures:
                    return fixtures, "API-Football"
            except Exception:
                pass
        return self.openfootball_client.world_cup_fixtures(), "OpenFootball"

    def _sync_odds(self) -> int:
        self.odds_source = "none"
        if self.odds_client.enabled:
            try:
                saved = self.repository.save_many_odds(self.odds_client.world_cup_odds())
                if saved:
                    self.odds_source = "The Odds API"
                    return saved
            except Exception:
                self.odds_source = "The Odds API unavailable"
        if self.api_football_client.enabled:
            try:
                saved = self.repository.save_many_odds(self.api_football_client.world_cup_odds())
                if saved:
                    self.odds_source = "API-Football"
                    return saved
            except Exception:
                if self.odds_source == "none":
                    self.odds_source = "unavailable"
        if self.odds_source == "none":
            self.odds_source = "unavailable"
        return 0

    def status(self) -> dict:
        stale = bool(self.last_error) or (self.last_success_at is None and self.last_sync_at is not None)
        return {
            "enabled": self.config.enabled,
            "running": self.running,
            "last_sync_at": _iso(self.last_sync_at),
            "last_success_at": _iso(self.last_success_at),
            "last_error": self.last_error,
            "fixture_source": self.fixture_source,
            "odds_source": self.odds_source,
            "current_result_team_profiles": self.current_result_team_profiles,
            "next_sync_at": _iso(self.next_sync_at),
            "stale": stale,
        }


async def run_auto_sync_loop(service: SyncService) -> None:
    while True:
        try:
            await asyncio.to_thread(service.sync, False, False)
        except Exception:
            pass
        await asyncio.sleep(service.config.interval_seconds)
