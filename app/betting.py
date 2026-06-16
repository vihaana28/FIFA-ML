from __future__ import annotations

from functools import reduce
from operator import mul
from typing import Iterable


def american_to_decimal(american_odds: int | float) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be 0")
    if american_odds > 0:
        return 1 + (american_odds / 100)
    return 1 + (100 / abs(american_odds))


def implied_probability(american_odds: int | float) -> float:
    if american_odds > 0:
        return 100 / (american_odds + 100)
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    raise ValueError("American odds cannot be 0")


def remove_vig(market_odds: dict[str, int | float]) -> dict[str, float]:
    raw = {key: implied_probability(value) for key, value in market_odds.items()}
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("Market probabilities must sum above 0")
    return {key: probability / total for key, probability in raw.items()}


def expected_value(model_probability: float, american_odds: int | float, stake: float = 1) -> float:
    decimal_odds = american_to_decimal(american_odds)
    profit_if_win = stake * (decimal_odds - 1)
    loss_if_lose = stake
    return (model_probability * profit_if_win) - ((1 - model_probability) * loss_if_lose)


def kelly_fraction(model_probability: float, american_odds: int | float) -> float:
    decimal_odds = american_to_decimal(american_odds)
    net_odds = decimal_odds - 1
    if net_odds <= 0:
        return 0
    fraction = ((net_odds * model_probability) - (1 - model_probability)) / net_odds
    return max(0, min(fraction, 1))


def parlay_outcome(legs: Iterable[dict], stake: float = 1) -> dict[str, float | int]:
    legs = list(legs)
    if not legs:
        raise ValueError("Parlay requires at least one leg")

    probabilities = [float(leg["probability"]) for leg in legs]
    decimal_odds = [american_to_decimal(float(leg["american_odds"])) for leg in legs]
    combined_probability = reduce(mul, probabilities, 1.0)
    combined_decimal = reduce(mul, decimal_odds, 1.0)
    payout = stake * combined_decimal
    profit = payout - stake

    return {
        "legs": len(legs),
        "combined_probability": combined_probability,
        "decimal_odds": combined_decimal,
        "payout": payout,
        "profit": profit,
        "expected_value": (combined_probability * profit) - ((1 - combined_probability) * stake),
    }

