"""Explainable cold-start priors; personal EWMA replaces them after observations."""

from payments.models import Category


CATEGORY_PRIORS_DAYS: dict[Category, float] = {
    Category.GROCERY: 14.0,
    Category.STATIONERY: 45.0,
    Category.HEALTH: 30.0,
    Category.SAAS_SUBSCRIPTION: 30.0,
    Category.OTHER: 30.0,
}


def cadence_prior_days(category: Category | str) -> float:
    return CATEGORY_PRIORS_DAYS[Category(category)]
