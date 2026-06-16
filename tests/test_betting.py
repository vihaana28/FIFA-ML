import pytest

from app.betting import (
    american_to_decimal,
    expected_value,
    implied_probability,
    kelly_fraction,
    parlay_outcome,
    remove_vig,
)


def test_american_odds_convert_to_decimal_and_implied_probability():
    assert american_to_decimal(-150) == pytest.approx(1.6667, rel=1e-3)
    assert american_to_decimal(220) == pytest.approx(3.2)
    assert implied_probability(-150) == pytest.approx(0.6)
    assert implied_probability(220) == pytest.approx(0.3125)


def test_remove_vig_normalizes_market_probabilities():
    fair = remove_vig({"home": -120, "draw": 260, "away": 320})

    assert sum(fair.values()) == pytest.approx(1.0)
    assert fair["home"] > fair["draw"] > fair["away"]


def test_expected_value_and_kelly_fraction_for_positive_edge():
    ev = expected_value(model_probability=0.62, american_odds=-120, stake=10)
    kelly = kelly_fraction(model_probability=0.62, american_odds=-120)

    assert ev > 0
    assert 0 < kelly < 1


def test_parlay_outcome_combines_probability_and_payout():
    result = parlay_outcome(
        legs=[
            {"label": "USA win", "probability": 0.58, "american_odds": -105},
            {"label": "Brazil win", "probability": 0.66, "american_odds": -140},
        ],
        stake=25,
    )

    assert result["combined_probability"] == pytest.approx(0.3828)
    assert result["decimal_odds"] > 2
    assert "expected_value" in result
