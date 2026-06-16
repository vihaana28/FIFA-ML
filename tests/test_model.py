import pytest

from app.model import TeamFeatures, predict_match, score_matrix, top_scorelines


def test_score_matrix_is_normalized_with_other_bucket():
    matrix = score_matrix(home_goals=1.6, away_goals=0.9, max_goals=5)

    assert sum(cell["probability"] for cell in matrix) == pytest.approx(1.0)
    assert any(cell["score"] == "other" for cell in matrix)


def test_prediction_returns_scorelines_and_wdl_probabilities():
    home = TeamFeatures(
        team_id="usa",
        team_name="USA",
        attack=1.12,
        defense=0.92,
        elo=1780,
        recent_form=0.62,
        player_strength=0.57,
    )
    away = TeamFeatures(
        team_id="mex",
        team_name="Mexico",
        attack=1.02,
        defense=1.03,
        elo=1715,
        recent_form=0.51,
        player_strength=0.52,
    )

    prediction = predict_match("fixture-1", home, away)

    assert prediction["fixture_id"] == "fixture-1"
    assert sum(prediction["wdl"].values()) == pytest.approx(1.0)
    assert prediction["top_scores"][0]["probability"] >= prediction["top_scores"][-1]["probability"]
    assert prediction["confidence"] in {"low", "medium", "high"}


def test_top_scorelines_excludes_other_bucket():
    matrix = score_matrix(home_goals=1.2, away_goals=1.1, max_goals=5)
    scores = top_scorelines(matrix, limit=3)

    assert len(scores) == 3
    assert all(score["score"] != "other" for score in scores)
