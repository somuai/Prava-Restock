"""Explainable cold-start priors; personal EWMA replaces them after observations."""

from payments.models import Category, _cold_start_category_priors


_FALLBACK_PRIOR_DAYS = 30.0


def cadence_prior_days(category: Category | str) -> float:
    """Return the public category prior, or a neutral benchmark fallback.

    This helper is for offline evaluation only. Onboarding retains the user's
    estimate when a category is not mapped; see ``TrackedItem``.
    """
    normalized = Category(category).value
    return _cold_start_category_priors().get(normalized, _FALLBACK_PRIOR_DAYS)
