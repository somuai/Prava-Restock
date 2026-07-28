# Restock Trigger Math

Stateless utility service for agents that calculate replenishment dates and compare two subscription prices.

https://restock-trigger-math-production.up.railway.app

## GET /health

Confirms that the public service is available.

```bash
curl -sS https://restock-trigger-math-production.up.railway.app/health
```

Illustrative response captured on 24 July 2026 (the `days_until_depletion`
value is evaluated on the day of each request):

```json
{"status":"healthy"}
```

## POST /predict-depletion

Calculates an expected depletion date and days remaining from a last-purchase date and a positive cadence.

```bash
curl -sS -X POST https://restock-trigger-math-production.up.railway.app/predict-depletion \
  -H 'Content-Type: application/json' \
  -d '{"last_purchased_at":"2026-07-10","typical_cadence_days":14}'
```

Example response:

```json
{"predicted_depletion_date":"2026-07-24","days_until_depletion":0}
```

## POST /evaluate-renewal

Compares a current plan price with an alternate price and returns the cheaper recommended action plus savings.

```bash
curl -sS -X POST https://restock-trigger-math-production.up.railway.app/evaluate-renewal \
  -H 'Content-Type: application/json' \
  -d '{"current_plan_amount":"2400.00","alternate_plan_amount":"2200.00"}'
```

Example response:

```json
{"recommended_action":"switch_to_alternate","savings_amount":"200.00"}
```

## Agent usage steps

1. Call `GET /health` before relying on the service.
2. Call `POST /predict-depletion` only when you know the ISO 8601 last-purchase date and a positive cadence in days.
3. Use the returned date and days remaining as a calculation, not proof that the user wants a purchase.
4. Call `POST /evaluate-renewal` when you have two positive prices in the same currency.
5. Treat `switch_to_alternate` as a recommendation; obtain explicit user approval before changing any plan.
6. Never send credentials, payment data, identity, or other sensitive data. This service is stateless and makes no merchant or payment calls.
