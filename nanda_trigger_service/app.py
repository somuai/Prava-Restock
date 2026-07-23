"""A standalone, side-effect-free service for replenishment trigger math.

This module intentionally does not import Restock persistence, payment, merchant,
or user-identity code.  Its two calculations can be called by any agent.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


app = FastAPI(
    title="Restock Trigger Math",
    version="1.0.0",
    description="Stateless depletion and renewal recommendation calculations for agents.",
)


class DepletionRequest(BaseModel):
    last_purchased_at: date
    typical_cadence_days: float = Field(gt=0)


class DepletionResponse(BaseModel):
    predicted_depletion_date: date
    days_until_depletion: int


class RenewalRequest(BaseModel):
    current_plan_amount: Decimal = Field(gt=0)
    alternate_plan_amount: Decimal = Field(gt=0)


class RenewalResponse(BaseModel):
    recommended_action: str
    savings_amount: Decimal


@app.get("/health")
def health() -> dict[str, str]:
    """Public liveness probe for a hosted deployment."""
    return {"status": "healthy"}


@app.get("/skill.md", response_class=PlainTextResponse)
def serve_skill_md() -> str:
    """Serve the SKILL.md manifest for NANDA Town agent discovery."""
    skill_path = Path(__file__).resolve().parent / "SKILL.md"
    return skill_path.read_text(encoding="utf-8")


@app.post("/predict-depletion", response_model=DepletionResponse)
def predict_depletion(request: DepletionRequest) -> DepletionResponse:
    """Predict the next depletion date from a purchase date and cadence."""
    # Timedelta accepts fractional days; returning a date keeps the public API
    # deterministic and deliberately simple for agent callers.
    depletion_date = request.last_purchased_at + timedelta(days=request.typical_cadence_days)
    return DepletionResponse(
        predicted_depletion_date=depletion_date,
        days_until_depletion=(depletion_date - date.today()).days,
    )


@app.post("/evaluate-renewal", response_model=RenewalResponse)
def evaluate_renewal(request: RenewalRequest) -> RenewalResponse:
    """Recommend the cheaper plan, with the exact amount saved if switching."""
    if request.alternate_plan_amount < request.current_plan_amount:
        return RenewalResponse(
            recommended_action="switch_to_alternate",
            savings_amount=request.current_plan_amount - request.alternate_plan_amount,
        )
    return RenewalResponse(recommended_action="renew_as_is", savings_amount=Decimal("0"))
