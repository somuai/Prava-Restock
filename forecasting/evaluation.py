"""Small dependency-free evaluator for candidate cadence models."""

from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(frozen=True)
class ForecastCase:
    predicted_interval_days: float
    actual_interval_days: float
    trigger_window_days: int = 2
    user_acted: bool = False


@dataclass(frozen=True)
class ForecastMetrics:
    mae_days: float
    trigger_precision: float
    missed_depletion_rate: float
    user_action_rate: float
    sample_count: int


def evaluate_predictions(cases: Iterable[ForecastCase]) -> ForecastMetrics:
    values = list(cases)
    if not values:
        return ForecastMetrics(0.0, 0.0, 0.0, 0.0, 0)
    errors = [abs(case.predicted_interval_days - case.actual_interval_days) for case in values]
    triggers = [case for case in values if case.predicted_interval_days - case.trigger_window_days <= case.actual_interval_days]
    useful = [case for case in triggers if abs(case.predicted_interval_days - case.actual_interval_days) <= case.trigger_window_days]
    missed = [case for case in values if case.predicted_interval_days > case.actual_interval_days + case.trigger_window_days]
    return ForecastMetrics(
        mae_days=mean(errors),
        trigger_precision=len(useful) / len(triggers) if triggers else 0.0,
        missed_depletion_rate=len(missed) / len(values),
        user_action_rate=sum(case.user_acted for case in values) / len(values),
        sample_count=len(values),
    )


def ewma_predictions(intervals: Iterable[float], initial: float, alpha: float = 0.3) -> list[float]:
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    cadence = initial
    predictions = []
    for interval in intervals:
        predictions.append(cadence)
        cadence = alpha * interval + (1 - alpha) * cadence
    return predictions
