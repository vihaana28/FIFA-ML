from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.data import TEAM_PRIORS
from app.learned_model import TrainingMatch
from app.model import TeamFeatures
from app.providers import OpenFootballClient, slugify
from app.stats_sources import aggregate_result_profiles


TEAM_NAME_ALIASES = {
    "united-states": "usa",
    "u-s-a": "usa",
    "usmnt": "usa",
    "czechia": "czech-republic",
    "korea-republic": "south-korea",
    "republic-of-korea": "south-korea",
    "turkiye": "turkey",
    "cote-d-ivoire": "ivory-coast",
    "cote-divoire": "ivory-coast",
    "cape-verde-islands": "cape-verde",
    "congo-dr": "dr-congo",
    "democratic-republic-of-congo": "dr-congo",
}


class Repository:
    def __init__(self, database_url: str = "data/fifa_ml.sqlite3"):
        if database_url != ":memory:":
            Path(database_url).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_url, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.init_schema()
        self.seed()
        self.refresh_fixture_team_features()

    def init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                group_name TEXT,
                rank INTEGER,
                provider TEXT,
                provider_team_id TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS team_features (
                team_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS player_features (
                team_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fixtures (
                id TEXT PRIMARY KEY,
                provider TEXT,
                provider_fixture_id TEXT,
                home_team_id TEXT NOT NULL,
                away_team_id TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                kickoff TEXT NOT NULL,
                venue TEXT,
                stage TEXT,
                status TEXT,
                score_payload TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS odds_snapshots (
                fixture_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                source TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS raw_api_cache (
                cache_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS predictions (
                fixture_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS simulated_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS recommendation_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS team_stat_profiles (
                team_id TEXT PRIMARY KEY,
                team_name TEXT NOT NULL,
                source TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS model_training_matches (
                source TEXT NOT NULL,
                match_date TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_score INTEGER NOT NULL,
                away_score INTEGER NOT NULL,
                tournament TEXT,
                neutral INTEGER DEFAULT 0,
                PRIMARY KEY (source, match_date, home_team, away_team)
            );
            CREATE TABLE IF NOT EXISTS player_stat_profiles (
                player_id TEXT PRIMARY KEY,
                team_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                source TEXT NOT NULL,
                payload TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._migrate_columns()
        self.connection.commit()

    def _migrate_columns(self) -> None:
        columns = {
            table: {row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})").fetchall()}
            for table in ("teams", "fixtures", "odds_snapshots")
        }
        if "provider" not in columns["teams"]:
            self.connection.execute("ALTER TABLE teams ADD COLUMN provider TEXT")
        if "provider_team_id" not in columns["teams"]:
            self.connection.execute("ALTER TABLE teams ADD COLUMN provider_team_id TEXT")
        if "updated_at" not in columns["teams"]:
            self.connection.execute("ALTER TABLE teams ADD COLUMN updated_at TEXT")
        if "provider" not in columns["fixtures"]:
            self.connection.execute("ALTER TABLE fixtures ADD COLUMN provider TEXT")
        if "provider_fixture_id" not in columns["fixtures"]:
            self.connection.execute("ALTER TABLE fixtures ADD COLUMN provider_fixture_id TEXT")
        if "updated_at" not in columns["fixtures"]:
            self.connection.execute("ALTER TABLE fixtures ADD COLUMN updated_at TEXT")
        if "status" not in columns["fixtures"]:
            self.connection.execute("ALTER TABLE fixtures ADD COLUMN status TEXT")
        if "score_payload" not in columns["fixtures"]:
            self.connection.execute("ALTER TABLE fixtures ADD COLUMN score_payload TEXT")
        if "source" not in columns["odds_snapshots"]:
            self.connection.execute("ALTER TABLE odds_snapshots ADD COLUMN source TEXT")
        if "updated_at" not in columns["odds_snapshots"]:
            self.connection.execute("ALTER TABLE odds_snapshots ADD COLUMN updated_at TEXT")

    def seed(self) -> None:
        if self.list_fixtures():
            return
        try:
            fixtures = OpenFootballClient().world_cup_fixtures()
        except Exception:
            fixtures = []
        if fixtures:
            self.replace_fixtures(fixtures)

    def _feature_for_team(self, team_id: str, team_name: str) -> TeamFeatures:
        team_slug = slugify(team_name)
        prior_key = team_id if team_id in TEAM_PRIORS else TEAM_NAME_ALIASES.get(team_slug, team_slug)
        prior = TEAM_PRIORS.get(prior_key)
        if not prior:
            prior = {
                "attack": 1.0,
                "defense": 1.05,
                "elo": 1650,
                "recent_form": 0.48,
                "player_strength": 0.48,
            }
        return TeamFeatures(team_id=team_id, team_name=team_name, **prior)

    def refresh_fixture_team_features(self) -> None:
        rows = self.connection.execute(
            """
            SELECT home_team_id AS team_id, home_team AS team_name FROM fixtures
            UNION
            SELECT away_team_id AS team_id, away_team AS team_name FROM fixtures
            """
        ).fetchall()
        for row in rows:
            stat_profile_row = self.connection.execute(
                "SELECT payload FROM team_stat_profiles WHERE team_id = ?",
                (row["team_id"],),
            ).fetchone()
            if stat_profile_row:
                features = self._feature_from_stat_profile(json.loads(stat_profile_row["payload"]))
            else:
                features = self._feature_for_team(row["team_id"], row["team_name"])
            self.connection.execute(
                "INSERT OR REPLACE INTO team_features (team_id, payload) VALUES (?, ?)",
                (row["team_id"], json.dumps(asdict(features))),
            )
            existing_player = self.connection.execute(
                "SELECT payload FROM player_features WHERE team_id = ?",
                (row["team_id"],),
            ).fetchone()
            if not existing_player:
                self.connection.execute(
                    "INSERT OR REPLACE INTO player_features (team_id, payload) VALUES (?, ?)",
                    (
                        row["team_id"],
                        json.dumps(
                            {
                                "team_id": row["team_id"],
                                "sample_size": 0,
                                "avg_rating": None,
                                "availability": 0.84,
                                "club_form_index": features.player_strength,
                                "source": "model-prior",
                            }
                        ),
                    ),
                )
        self.connection.commit()

    def _feature_from_stat_profile(self, item: dict) -> TeamFeatures:
        base = self._feature_for_team(item["team_id"], item["team_name"])
        if item.get("source") == "World Football Elo":
            elo = int(item.get("elo") or base.elo)
            strength = float(item.get("elo_strength") or (elo / 1800))
            return TeamFeatures(
                team_id=base.team_id,
                team_name=base.team_name,
                attack=max(0.55, min(1.65, (base.attack * 0.82) + (strength * 0.18))),
                defense=max(0.70, min(1.35, (base.defense * 0.88) + ((2 - strength) * 0.08))),
                elo=elo,
                recent_form=base.recent_form,
                player_strength=base.player_strength,
            )
        if item.get("source") == "Player Availability":
            availability = float(item.get("availability") or 1.0)
            attack_availability = float(item.get("attack_availability") or availability)
            defense_availability = float(item.get("defense_availability") or availability)
            return TeamFeatures(
                team_id=base.team_id,
                team_name=base.team_name,
                attack=max(0.55, min(1.65, base.attack * attack_availability)),
                defense=max(0.70, min(1.35, base.defense * (1 + ((1 - defense_availability) * 0.25)))),
                elo=base.elo,
                recent_form=base.recent_form,
                player_strength=max(0.25, min(0.85, base.player_strength * availability)),
            )
        matches = max(1, int(item.get("matches") or 1))
        weighted_matches = max(0.01, float(item.get("weighted_matches") or 0))
        if item.get("source") == "International Results + Friendlies" and weighted_matches:
            goals_per_match = float(item.get("weighted_goals") or 0) / weighted_matches
            goals_against_per_match = float(item.get("weighted_goals_against") or 0) / weighted_matches
        else:
            goals_per_match = float(item.get("goals") or 0) / matches
            goals_against_per_match = float(item.get("goals_against") or 0) / matches
        xg_per_match = float(item.get("xg_for") or 0) / matches
        shots_per_match = float(item.get("shots") or 0) / matches
        pass_volume = min(1.0, float(item.get("passes") or 0) / (matches * 650))
        pressure_volume = min(1.0, float(item.get("pressures") or 0) / (matches * 220))

        attack_signal = xg_per_match if xg_per_match else goals_per_match
        shot_signal = shots_per_match / 14 if shots_per_match else goals_per_match / 2.5
        attack = max(0.55, min(1.65, (base.attack * 0.55) + (attack_signal / 1.5 * 0.30) + (shot_signal * 0.15)))
        defense = max(0.70, min(1.35, base.defense - (pressure_volume * 0.10) + (goals_against_per_match * 0.08)))
        recent_form = max(0.25, min(0.82, (base.recent_form * 0.65) + (goals_per_match / 2.2 * 0.20) + (pass_volume * 0.15)))
        player_strength = max(0.25, min(0.85, (base.player_strength * 0.70) + (xg_per_match / 1.8 * 0.20) + (pass_volume * 0.10)))
        if item.get("source") == "International Results + Friendlies":
            attack = max(0.55, min(1.65, attack * float(item.get("attack_multiplier") or 1.0)))
            defense = max(0.70, min(1.35, defense * float(item.get("defense_multiplier") or 1.0)))
            recent_form = max(0.25, min(0.82, (recent_form * 0.55) + (float(item.get("recent_form_score") or recent_form) * 0.45)))
            player_strength = max(0.25, min(0.85, player_strength * 0.92))
        return TeamFeatures(
            team_id=base.team_id,
            team_name=base.team_name,
            attack=attack,
            defense=defense,
            elo=base.elo,
            recent_form=recent_form,
            player_strength=player_strength,
        )

    def replace_fixtures(self, fixtures: list[dict]) -> dict:
        existing = {fixture["id"]: fixture for fixture in self.list_fixtures()}
        changed_fixture_ids = [
            fixture["id"]
            for fixture in fixtures
            if fixture["id"] not in existing
            or existing[fixture["id"]].get("status") != fixture.get("status", "SCHEDULED")
            or existing[fixture["id"]].get("score") != fixture.get("score")
        ]
        self.connection.execute("DELETE FROM fixtures")
        seen_teams: dict[str, str] = {}
        for fixture in fixtures:
            seen_teams[fixture["home_team_id"]] = fixture["home_team"]
            seen_teams[fixture["away_team_id"]] = fixture["away_team"]
            self.connection.execute(
                """
                INSERT OR REPLACE INTO fixtures
                (id, provider, provider_fixture_id, home_team_id, away_team_id, home_team, away_team, kickoff, venue, stage, status, score_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fixture["id"],
                    fixture.get("provider"),
                    fixture.get("provider_fixture_id"),
                    fixture["home_team_id"],
                    fixture["away_team_id"],
                    fixture["home_team"],
                    fixture["away_team"],
                    fixture["kickoff"],
                    fixture.get("venue", ""),
                    fixture.get("stage", "World Cup"),
                    fixture.get("status", "SCHEDULED"),
                    json.dumps(fixture.get("score")),
                ),
            )
        for team_id, team_name in seen_teams.items():
            self.connection.execute(
                """
                INSERT OR REPLACE INTO teams
                (id, name, group_name, rank, provider, provider_team_id)
                VALUES (?, ?, COALESCE((SELECT group_name FROM teams WHERE id = ?), ''), NULL, 'fixture-sync', ?)
                """,
                (team_id, team_name, team_id, team_id),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO team_features (team_id, payload) VALUES (?, ?)",
                (team_id, json.dumps(asdict(self._feature_for_team(team_id, team_name)))),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO player_features (team_id, payload) VALUES (?, ?)",
                (
                    team_id,
                    json.dumps(
                        {
                            "team_id": team_id,
                            "sample_size": 0,
                            "avg_rating": None,
                            "availability": 0.84,
                            "club_form_index": self._feature_for_team(team_id, team_name).player_strength,
                            "source": "model-prior",
                        }
                    ),
                ),
            )
        self.connection.commit()
        self.refresh_fixture_team_features()
        return {"fixtures": len(fixtures), "changed_fixture_ids": changed_fixture_ids}

    def cache_raw(self, cache_key: str, provider: str, payload: dict | list) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO raw_api_cache (cache_key, provider, payload) VALUES (?, ?, ?)",
            (cache_key, provider, json.dumps(payload)),
        )
        self.connection.commit()

    def list_fixtures(self) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM fixtures ORDER BY kickoff").fetchall()
        return [self._fixture_from_row(row) for row in rows]

    def get_fixture(self, fixture_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM fixtures WHERE id = ?", (fixture_id,)).fetchone()
        return self._fixture_from_row(row) if row else None

    @staticmethod
    def _fixture_from_row(row: sqlite3.Row) -> dict:
        item = dict(row)
        if item.get("score_payload"):
            item["score"] = json.loads(item["score_payload"])
        item.pop("score_payload", None)
        return item

    def get_team_features(self, team_id: str) -> TeamFeatures:
        row = self.connection.execute("SELECT payload FROM team_features WHERE team_id = ?", (team_id,)).fetchone()
        if not row:
            raise KeyError(f"No features for team {team_id}")
        return TeamFeatures(**json.loads(row["payload"]))

    def get_player_features(self, team_id: str) -> dict:
        row = self.connection.execute("SELECT payload FROM player_features WHERE team_id = ?", (team_id,)).fetchone()
        return json.loads(row["payload"]) if row else {"team_id": team_id, "sample_size": 0}

    def save_stat_profiles(self, team_profiles: list[dict], player_profiles: list[dict]) -> None:
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO team_stat_profiles (team_id, team_name, source, payload)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    item["team_id"],
                    item["team_name"],
                    item.get("source", "unknown"),
                    json.dumps(item),
                )
                for item in team_profiles
            ],
        )
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO player_stat_profiles (player_id, team_id, player_name, source, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    str(item["player_id"]),
                    item["team_id"],
                    item["player_name"],
                    item.get("source", "unknown"),
                    json.dumps(item),
                )
                for item in player_profiles
            ],
        )
        for item in team_profiles:
            self.connection.execute(
                "INSERT OR REPLACE INTO team_features (team_id, payload) VALUES (?, ?)",
                (item["team_id"], json.dumps(asdict(self._feature_from_stat_profile(item)))),
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO player_features (team_id, payload) VALUES (?, ?)",
                (
                    item["team_id"],
                    json.dumps(
                        {
                            "team_id": item["team_id"],
                            "sample_size": item.get("lineup_players", 0),
                            "avg_rating": None,
                            "availability": item.get("availability", 0.88 if item.get("lineup_players", 0) else 0.80),
                            "missing_key_players": item.get("missing_key_players", 0),
                            "club_form_index": self._feature_from_stat_profile(item).player_strength,
                            "source": item.get("source", "unknown"),
                        }
                    ),
                ),
            )
        self.connection.commit()

    def refresh_current_result_stats(self) -> dict:
        self.connection.execute("DELETE FROM team_stat_profiles WHERE source = ?", ("football-data.org Results",))
        self.connection.execute("DELETE FROM player_stat_profiles WHERE source = ?", ("football-data.org Results",))
        profiles = aggregate_result_profiles(self.list_fixtures())
        self.save_stat_profiles(profiles["team_profiles"], profiles["player_profiles"])
        return {
            "team_profiles": len(profiles["team_profiles"]),
            "player_profiles": len(profiles["player_profiles"]),
            "source": "football-data.org Results",
        }

    def list_team_stats(self) -> list[dict]:
        rows = self.connection.execute("SELECT payload FROM team_stat_profiles ORDER BY team_name").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_team_stats(self, team_id: str) -> dict | None:
        row = self.connection.execute("SELECT payload FROM team_stat_profiles WHERE team_id = ?", (team_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def save_training_matches(self, matches: list[TrainingMatch]) -> int:
        self.connection.executemany(
            """
            INSERT OR REPLACE INTO model_training_matches
            (source, match_date, home_team, away_team, home_score, away_score, tournament, neutral)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    match.source,
                    match.match_date.isoformat(),
                    match.home_team,
                    match.away_team,
                    match.home_score,
                    match.away_score,
                    match.tournament,
                    1 if match.neutral else 0,
                )
                for match in matches
            ],
        )
        self.connection.commit()
        return len(matches)

    def list_training_matches(self) -> list[TrainingMatch]:
        rows = self.connection.execute(
            """
            SELECT source, match_date, home_team, away_team, home_score, away_score, tournament, neutral
            FROM model_training_matches
            ORDER BY match_date, home_team, away_team
            """
        ).fetchall()
        return [
            TrainingMatch(
                source=row["source"],
                match_date=date.fromisoformat(row["match_date"]),
                home_team=row["home_team"],
                away_team=row["away_team"],
                home_score=int(row["home_score"]),
                away_score=int(row["away_score"]),
                tournament=row["tournament"] or "",
                neutral=bool(row["neutral"]),
            )
            for row in rows
        ]

    def get_saved_prediction(self, fixture_id: str) -> dict | None:
        row = self.connection.execute("SELECT payload FROM predictions WHERE fixture_id = ?", (fixture_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def delete_predictions(self, fixture_ids: list[str]) -> int:
        if not fixture_ids:
            return 0
        self.connection.executemany("DELETE FROM predictions WHERE fixture_id = ?", [(fixture_id,) for fixture_id in fixture_ids])
        deleted = self.connection.total_changes
        self.connection.commit()
        return deleted

    def list_player_stats(self, team_id: str | None = None, limit: int = 100) -> list[dict]:
        if team_id:
            rows = self.connection.execute(
                "SELECT payload FROM player_stat_profiles WHERE team_id = ? ORDER BY player_name LIMIT ?",
                (team_id, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload FROM player_stat_profiles ORDER BY player_name LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_odds(self, fixture_id: str) -> dict:
        row = self.connection.execute("SELECT payload FROM odds_snapshots WHERE fixture_id = ?", (fixture_id,)).fetchone()
        return json.loads(row["payload"]) if row else {}

    def save_odds(self, fixture_id: str, payload: dict) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO odds_snapshots (fixture_id, payload, source) VALUES (?, ?, ?)",
            (fixture_id, json.dumps(payload), payload.get("source", "unknown")),
        )
        self.connection.commit()

    def save_many_odds(self, snapshots: list[dict]) -> int:
        fixtures = self.list_fixtures()
        saved = 0
        for snapshot in snapshots:
            fixture_id = snapshot.get("fixture_id")
            if not fixture_id:
                fixture_id = self.match_fixture_id(snapshot.get("home_team", ""), snapshot.get("away_team", ""))
            if not fixture_id:
                continue
            payload = {
                **snapshot.get("market", {}),
                "source": snapshot.get("source", "unknown"),
                "last_updated": snapshot.get("last_updated") or snapshot.get("commence_time"),
            }
            self.save_odds(fixture_id, payload)
            saved += 1
        return saved

    def match_fixture_id(self, home_team: str, away_team: str) -> str | None:
        home_slug = slugify(home_team)
        away_slug = slugify(away_team)
        for fixture in self.list_fixtures():
            if slugify(fixture["home_team"]) == home_slug and slugify(fixture["away_team"]) == away_slug:
                return fixture["id"]
            if slugify(fixture["home_team"]) == away_slug and slugify(fixture["away_team"]) == home_slug:
                return fixture["id"]
        return None

    def save_prediction(self, fixture_id: str, payload: dict) -> None:
        self.connection.execute(
            "INSERT OR REPLACE INTO predictions (fixture_id, payload) VALUES (?, ?)",
            (fixture_id, json.dumps(payload)),
        )
        self.connection.commit()

    def save_bet(self, payload: dict) -> None:
        self.connection.execute("INSERT INTO simulated_bets (payload) VALUES (?)", (json.dumps(payload),))
        self.connection.commit()

    def save_recommendations(self, payload: dict) -> None:
        self.connection.execute("INSERT INTO recommendation_records (payload) VALUES (?)", (json.dumps(payload),))
        self.connection.commit()
