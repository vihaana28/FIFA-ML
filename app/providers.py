from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
import urllib.parse
import urllib.request


def slugify(value: str) -> str:
    value = value.lower().replace("&", " ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def _is_placeholder_team(name: str) -> bool:
    return bool(re.search(r"\d|/", name)) or name.startswith(("W", "L"))


def _parse_openfootball_datetime(date_value: str, time_value: str) -> str:
    match = re.match(r"(?P<hour>\d{1,2}):(?P<minute>\d{2}) UTC(?P<offset>[+-]\d{1,2})", time_value)
    if not match:
        return f"{date_value}T00:00:00+00:00"
    offset_hours = int(match.group("offset"))
    offset = timezone(timedelta(hours=offset_hours))
    kickoff = datetime(
        int(date_value[0:4]),
        int(date_value[5:7]),
        int(date_value[8:10]),
        int(match.group("hour")),
        int(match.group("minute")),
        tzinfo=offset,
    )
    return kickoff.isoformat()


def _decimal_to_american(decimal_value: float) -> int:
    if decimal_value >= 2:
        return round((decimal_value - 1) * 100)
    return round(-100 / (decimal_value - 1))


class ApiFootballClient:
    base_url = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def get(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        if not self.api_key:
            raise RuntimeError("API_FOOTBALL_KEY is not configured")
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        request = urllib.request.Request(url, headers={"x-apisports-key": self.api_key})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def world_cup_fixtures(self) -> list[dict]:
        return self.parse_fixtures(self.get("/fixtures", {"league": 1, "season": 2026}))

    def world_cup_odds(self) -> list[dict]:
        return self.parse_odds(self.get("/odds", {"league": 1, "season": 2026, "bet": 1}))

    @staticmethod
    def parse_fixtures(payload: dict) -> list[dict]:
        fixtures = []
        for item in payload.get("response", []):
            fixture = item.get("fixture", {})
            teams = item.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            venue = fixture.get("venue") or {}
            venue_parts = [part for part in [venue.get("name"), venue.get("city")] if part]
            provider_id = str(fixture.get("id"))
            fixtures.append(
                {
                    "id": f"api-football-{provider_id}",
                    "provider": "api-football",
                    "provider_fixture_id": provider_id,
                    "home_team_id": str(home.get("id") or slugify(home.get("name", ""))),
                    "away_team_id": str(away.get("id") or slugify(away.get("name", ""))),
                    "home_team": home.get("name", ""),
                    "away_team": away.get("name", ""),
                    "kickoff": fixture.get("date", ""),
                    "venue": ", ".join(venue_parts),
                    "stage": (item.get("league") or {}).get("round", "World Cup"),
                }
            )
        return fixtures

    @staticmethod
    def parse_odds(payload: dict) -> list[dict]:
        snapshots = []
        for item in payload.get("response", []):
            fixture_id = str((item.get("fixture") or {}).get("id", ""))
            bookmakers = item.get("bookmakers") or []
            for bookmaker in bookmakers[:1]:
                for bet in bookmaker.get("bets", []):
                    if str(bet.get("name", "")).lower() not in {"match winner", "1x2"}:
                        continue
                    values = {str(value.get("value", "")).lower(): value.get("odd") for value in bet.get("values", [])}
                    try:
                        snapshots.append(
                            {
                                "provider_fixture_id": fixture_id,
                                "source": f"API-Football / {bookmaker.get('name', 'bookmaker')}",
                                "market": {
                                    "home": _decimal_to_american(float(values.get("home"))),
                                    "draw": _decimal_to_american(float(values.get("draw"))),
                                    "away": _decimal_to_american(float(values.get("away"))),
                                },
                            }
                        )
                    except (TypeError, ValueError):
                        continue
        return snapshots


class FootballDataClient:
    base_url = "https://api.football-data.org/v4"

    def __init__(self, api_token: str | None = None):
        self.api_token = api_token or os.getenv("FOOTBALL_DATA_TOKEN")

    @property
    def enabled(self) -> bool:
        return bool(self.api_token)

    def get(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        if not self.api_token:
            raise RuntimeError("FOOTBALL_DATA_TOKEN is not configured")
        query = urllib.parse.urlencode(params or {})
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        request = urllib.request.Request(url, headers={"X-Auth-Token": self.api_token})
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def world_cup_matches(self) -> list[dict]:
        return self.parse_matches(self.get("/competitions/WC/matches"))

    @staticmethod
    def parse_matches(payload: dict) -> list[dict]:
        fixtures = []
        for item in payload.get("matches", []):
            home = item.get("homeTeam") or {}
            away = item.get("awayTeam") or {}
            home_name = home.get("name") or home.get("shortName") or ""
            away_name = away.get("name") or away.get("shortName") or ""
            if not home_name or not away_name or _is_placeholder_team(home_name) or _is_placeholder_team(away_name):
                continue
            score = item.get("score") or {}
            full_time = score.get("fullTime") or {}
            group = item.get("group")
            stage = item.get("stage") or "World Cup"
            provider_id = str(item.get("id"))
            fixtures.append(
                {
                    "id": f"football-data-{provider_id}",
                    "provider": "football-data",
                    "provider_fixture_id": provider_id,
                    "home_team_id": str(home.get("id") or slugify(home_name)),
                    "away_team_id": str(away.get("id") or slugify(away_name)),
                    "home_team": home_name,
                    "away_team": away_name,
                    "kickoff": item.get("utcDate", ""),
                    "venue": "",
                    "stage": f"{group} - {stage}" if group else stage,
                    "status": item.get("status", "SCHEDULED"),
                    "score": {
                        "home": full_time.get("home"),
                        "away": full_time.get("away"),
                        "winner": score.get("winner"),
                    },
                }
            )
        return fixtures


class TheOddsApiClient:
    base_url = "https://api.the-odds-api.com/v4"

    def __init__(self, api_key: str | None = None, regions: str | None = None, markets: str | None = None):
        self.api_key = api_key or os.getenv("THE_ODDS_API_KEY")
        self.regions = regions or os.getenv("ODDS_REGIONS", "us")
        self.markets = markets or os.getenv("ODDS_MARKETS", "h2h,spreads,totals")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def get(self, path: str, params: dict[str, str | int] | None = None) -> list | dict:
        if not self.api_key:
            raise RuntimeError("THE_ODDS_API_KEY is not configured")
        query = urllib.parse.urlencode({"apiKey": self.api_key, **(params or {})})
        with urllib.request.urlopen(f"{self.base_url}{path}?{query}", timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def discover_world_cup_sport_key(self) -> str | None:
        sports = self.get("/sports", {"all": "true"})
        return self.pick_world_cup_sport_key(sports)

    @staticmethod
    def pick_world_cup_sport_key(sports: list[dict]) -> str | None:
        active_soccer = [sport for sport in sports if sport.get("active") and "soccer" in str(sport.get("key", "")).lower()]
        exact = [
            sport
            for sport in active_soccer
            if str(sport.get("key")) == "soccer_fifa_world_cup"
            or (
                str(sport.get("title", "")).lower() == "fifa world cup"
                and "club" not in str(sport.get("description", "")).lower()
            )
        ]
        if exact:
            return str(exact[0]["key"])
        fallback = [
            sport
            for sport in active_soccer
            if "world cup" in str(sport.get("title", "")).lower()
            and "club" not in str(sport.get("title", "")).lower()
        ]
        return str(fallback[0]["key"]) if fallback else None

    def world_cup_odds(self) -> list[dict]:
        sport_key = self.discover_world_cup_sport_key()
        if not sport_key:
            return []
        payload = self.get(
            f"/sports/{sport_key}/odds",
            {"regions": self.regions, "markets": self.markets, "oddsFormat": "american"},
        )
        return self.normalize_h2h(payload)

    @staticmethod
    def normalize_h2h(payload: list[dict]) -> list[dict]:
        snapshots = []
        for event in payload:
            for bookmaker in event.get("bookmakers", [])[:1]:
                h2h = next((market for market in bookmaker.get("markets", []) if market.get("key") == "h2h"), None)
                if not h2h:
                    continue
                outcomes = {item["name"]: item["price"] for item in h2h.get("outcomes", [])}
                home = event.get("home_team")
                away = event.get("away_team")
                if home not in outcomes or away not in outcomes or "Draw" not in outcomes:
                    continue
                snapshots.append(
                    {
                        "provider_event_id": event.get("id"),
                        "home_team": home,
                        "away_team": away,
                        "commence_time": event.get("commence_time"),
                        "source": f"The Odds API / {bookmaker.get('title', bookmaker.get('key', 'bookmaker'))}",
                        "market": {"home": outcomes[home], "away": outcomes[away], "draw": outcomes["Draw"]},
                    }
                )
        return snapshots


class OpenFootballClient:
    url = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
    _cached_payload: dict | None = None

    def fetch_schedule(self) -> dict:
        if self.__class__._cached_payload is not None:
            return self.__class__._cached_payload
        with urllib.request.urlopen(self.url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.__class__._cached_payload = payload
        return payload

    def world_cup_fixtures(self) -> list[dict]:
        return self.parse_schedule(self.fetch_schedule())

    @staticmethod
    def parse_schedule(payload: dict) -> list[dict]:
        fixtures = []
        for match in payload.get("matches", []):
            home = str(match.get("team1", "")).strip()
            away = str(match.get("team2", "")).strip()
            if not home or not away or _is_placeholder_team(home) or _is_placeholder_team(away):
                continue
            group = match.get("group")
            round_name = match.get("round", "World Cup")
            stage = f"{group} - {round_name}" if group else round_name
            fixture_id = f"openfootball-{match.get('date')}-{slugify(home)}-{slugify(away)}"
            fixtures.append(
                {
                    "id": fixture_id,
                    "provider": "openfootball",
                    "provider_fixture_id": fixture_id,
                    "home_team_id": slugify(home),
                    "away_team_id": slugify(away),
                    "home_team": home,
                    "away_team": away,
                    "kickoff": _parse_openfootball_datetime(match.get("date", ""), match.get("time", "")),
                    "venue": match.get("ground", ""),
                    "stage": stage,
                }
            )
        return fixtures
