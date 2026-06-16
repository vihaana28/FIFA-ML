import pytest

from app.stats_sources import StatsBombOpenDataClient, aggregate_result_profiles, aggregate_statsbomb_match


def test_statsbomb_finds_world_cup_competitions():
    competitions = [
        {"competition_id": 43, "season_id": 106, "competition_name": "FIFA World Cup", "season_name": "2022"},
        {"competition_id": 11, "season_id": 90, "competition_name": "La Liga", "season_name": "2020/2021"},
    ]

    assert StatsBombOpenDataClient.world_cup_competitions(competitions) == [
        {"competition_id": 43, "season_id": 106, "season_name": "2022"}
    ]


def test_statsbomb_aggregates_team_and_player_event_stats():
    match = {
        "match_id": 3869685,
        "home_team": {"home_team_name": "Argentina"},
        "away_team": {"away_team_name": "France"},
    }
    events = [
        {
            "type": {"name": "Shot"},
            "team": {"name": "Argentina"},
            "player": {"id": 5503, "name": "Lionel Messi"},
            "shot": {"statsbomb_xg": 0.42, "outcome": {"name": "Goal"}},
        },
        {
            "type": {"name": "Shot"},
            "team": {"name": "France"},
            "player": {"id": 3009, "name": "Kylian Mbappé"},
            "shot": {"statsbomb_xg": 0.28, "outcome": {"name": "Saved"}},
        },
        {
            "type": {"name": "Pass"},
            "team": {"name": "Argentina"},
            "player": {"id": 5503, "name": "Lionel Messi"},
            "pass": {"goal_assist": True},
        },
        {
            "type": {"name": "Pressure"},
            "team": {"name": "France"},
            "player": {"id": 3009, "name": "Kylian Mbappé"},
        },
    ]
    lineups = [
        {"team_name": "Argentina", "lineup": [{"player_id": 5503, "player_name": "Lionel Messi"}]},
        {"team_name": "France", "lineup": [{"player_id": 3009, "player_name": "Kylian Mbappé"}]},
    ]

    profile = aggregate_statsbomb_match(match, events, lineups)

    argentina = profile["teams"]["argentina"]
    messi = profile["players"]["5503"]
    assert argentina["shots"] == 1
    assert argentina["goals"] == 1
    assert argentina["xg_for"] == pytest.approx(0.42)
    assert argentina["passes"] == 1
    assert messi["shots"] == 1
    assert messi["goals"] == 1
    assert messi["assists"] == 1
    assert messi["xg"] == pytest.approx(0.42)


def test_aggregate_result_profiles_updates_played_world_cup_matches():
    fixtures = [
        {
            "home_team_id": "769",
            "away_team_id": "774",
            "home_team": "Mexico",
            "away_team": "South Africa",
            "status": "FINISHED",
            "score": {"home": 2, "away": 0, "winner": "HOME_TEAM"},
        },
        {
            "home_team_id": "100",
            "away_team_id": "101",
            "home_team": "Future Team",
            "away_team": "Other Team",
            "status": "TIMED",
            "score": {"home": None, "away": None, "winner": None},
        },
    ]

    profiles = aggregate_result_profiles(fixtures)
    mexico = next(item for item in profiles["team_profiles"] if item["team_id"] == "769")
    south_africa = next(item for item in profiles["team_profiles"] if item["team_id"] == "774")

    assert mexico["source"] == "football-data.org Results"
    assert mexico["matches"] == 1
    assert mexico["goals"] == 2
    assert mexico["goals_against"] == 0
    assert mexico["wins"] == 1
    assert mexico["points"] == 3
    assert south_africa["losses"] == 1
