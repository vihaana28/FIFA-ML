import pytest

from app.providers import ApiFootballClient, FootballDataClient, OpenFootballClient, TheOddsApiClient


def test_openfootball_parses_real_world_cup_schedule_rows():
    payload = {
        "name": "World Cup 2026",
        "matches": [
            {
                "round": "Matchday 2",
                "date": "2026-06-12",
                "time": "15:00 UTC-4",
                "team1": "Canada",
                "team2": "Bosnia & Herzegovina",
                "group": "Group B",
                "ground": "Toronto",
            },
            {
                "round": "Round of 32",
                "num": 73,
                "date": "2026-06-28",
                "time": "12:00 UTC-7",
                "team1": "2A",
                "team2": "2B",
                "ground": "Los Angeles (Inglewood)",
            },
        ],
    }

    fixtures = OpenFootballClient.parse_schedule(payload)

    assert fixtures == [
        {
            "id": "openfootball-2026-06-12-canada-bosnia-herzegovina",
            "provider": "openfootball",
            "provider_fixture_id": "openfootball-2026-06-12-canada-bosnia-herzegovina",
            "home_team_id": "canada",
            "away_team_id": "bosnia-herzegovina",
            "home_team": "Canada",
            "away_team": "Bosnia & Herzegovina",
            "kickoff": "2026-06-12T15:00:00-04:00",
            "venue": "Toronto",
            "stage": "Group B - Matchday 2",
        }
    ]


def test_api_football_parses_fixture_response():
    payload = {
        "response": [
            {
                "fixture": {
                    "id": 123,
                    "date": "2026-06-12T22:00:00+00:00",
                    "venue": {"name": "SoFi Stadium", "city": "Inglewood"},
                },
                "league": {"round": "Group Stage - 1"},
                "teams": {
                    "home": {"id": 2384, "name": "USA"},
                    "away": {"id": 13, "name": "Paraguay"},
                },
            }
        ]
    }

    fixtures = ApiFootballClient.parse_fixtures(payload)

    assert fixtures[0]["id"] == "api-football-123"
    assert fixtures[0]["home_team"] == "USA"
    assert fixtures[0]["away_team_id"] == "13"
    assert fixtures[0]["venue"] == "SoFi Stadium, Inglewood"


def test_the_odds_api_normalizes_h2h_market():
    payload = [
        {
            "id": "evt_1",
            "home_team": "Canada",
            "away_team": "Bosnia & Herzegovina",
            "commence_time": "2026-06-12T19:00:00Z",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Canada", "price": 145},
                                {"name": "Bosnia & Herzegovina", "price": 210},
                                {"name": "Draw", "price": 230},
                            ],
                        }
                    ],
                }
            ],
        }
    ]

    odds = TheOddsApiClient.normalize_h2h(payload)

    assert odds[0]["home_team"] == "Canada"
    assert odds[0]["market"] == {"home": 145, "away": 210, "draw": 230}
    assert odds[0]["source"] == "The Odds API / DraftKings"


def test_the_odds_api_discovers_active_fifa_world_cup_before_club_world_cup():
    sports = [
        {"key": "soccer_fifa_club_world_cup", "title": "FIFA Club World Cup", "description": "FIFA Club World Cup", "active": False},
        {"key": "soccer_fifa_world_cup", "title": "FIFA World Cup", "description": "FIFA World Cup 2026", "active": True},
    ]

    assert TheOddsApiClient.pick_world_cup_sport_key(sports) == "soccer_fifa_world_cup"


def test_football_data_parses_world_cup_matches_with_scores():
    payload = {
        "matches": [
            {
                "id": 537327,
                "utcDate": "2026-06-11T19:00:00Z",
                "status": "FINISHED",
                "matchday": 1,
                "stage": "GROUP_STAGE",
                "group": "GROUP_A",
                "homeTeam": {"id": 769, "name": "Mexico", "shortName": "Mexico", "tla": "MEX"},
                "awayTeam": {"id": 774, "name": "South Africa", "shortName": "South Africa", "tla": "RSA"},
                "score": {"winner": "HOME_TEAM", "fullTime": {"home": 2, "away": 0}},
            }
        ]
    }

    fixtures = FootballDataClient.parse_matches(payload)

    assert fixtures == [
        {
            "id": "football-data-537327",
            "provider": "football-data",
            "provider_fixture_id": "537327",
            "home_team_id": "769",
            "away_team_id": "774",
            "home_team": "Mexico",
            "away_team": "South Africa",
            "kickoff": "2026-06-11T19:00:00Z",
            "venue": "",
            "stage": "GROUP_A - GROUP_STAGE",
            "status": "FINISHED",
            "score": {"home": 2, "away": 0, "winner": "HOME_TEAM"},
        }
    ]


def test_football_data_skips_unassigned_knockout_placeholders():
    payload = {
        "matches": [
            {
                "id": 537400,
                "utcDate": "2026-06-28T19:00:00Z",
                "status": "TIMED",
                "stage": "LAST_32",
                "homeTeam": {"id": None, "name": None, "shortName": None, "tla": None},
                "awayTeam": {"id": None, "name": None, "shortName": None, "tla": None},
                "score": {"fullTime": {"home": None, "away": None}},
            }
        ]
    }

    assert FootballDataClient.parse_matches(payload) == []
