from __future__ import annotations


CALIBRATION_WEIGHTS = {"high": 0.15, "medium": 0.35, "low": 0.60}


def _normalize(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values()) or 1.0
    return {key: value / total for key, value in values.items()}


def calibrate_wdl(model: dict[str, float], market: dict[str, float] | None, confidence: str) -> dict[str, float]:
    if not market or set(model) != set(market):
        return _normalize(dict(model))
    market_weight = CALIBRATION_WEIGHTS.get(confidence, CALIBRATION_WEIGHTS["medium"])
    calibrated = {
        outcome: (float(model[outcome]) * (1 - market_weight)) + (float(market[outcome]) * market_weight)
        for outcome in model
    }
    return _normalize(calibrated)


def calibration_payload(model: dict[str, float], market: dict[str, float] | None, confidence: str) -> dict:
    calibrated = calibrate_wdl(model, market, confidence)
    return {
        "method": "market-blend" if market else "none",
        "market_weight": CALIBRATION_WEIGHTS.get(confidence, CALIBRATION_WEIGHTS["medium"]) if market else 0.0,
        "wdl": calibrated,
    }
