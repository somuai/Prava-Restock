---
name: restock-trigger-math
description: Stateless utility service for agents that need a simple depletion-date calculation or a transparent subscription-renewal recommendation. Use when an agent needs to predict when a household consumable will run out, or when comparing two subscription plan prices.
version: 1.0.0
license: MIT
---

# Service Name: Restock Trigger Math

## Description

A stateless, side-effect-free utility that exposes two calculations useful to any AI agent managing recurring purchases or subscription renewals:

1. **Depletion prediction** — given a last-purchase date and a typical reorder cadence, returns the predicted depletion date and days remaining.
2. **Renewal evaluation** — given a current plan amount and an alternate plan amount, recommends the cheaper option and reports the exact savings.

No user data, no credentials, no payment logic. Pure math, deliberately generic so any agent could call it.

## Web Address

https://restock-trigger-math.up.railway.app

## Endpoints

- **GET /health**: Liveness probe.
  - **Response:**
    ```json
    {"status": "healthy"}
    ```

- **POST /predict-depletion**: Calculate the predicted depletion date.
  - **Headers:** `Content-Type: application/json`
  - **Body:**
    ```json
    {
      "last_purchased_at": "2026-07-10",
      "typical_cadence_days": 14
    }
    ```
  - **Response:**
    ```json
    {
      "predicted_depletion_date": "2026-07-24",
      "days_until_depletion": 0
    }
    ```
  - **Validation:** `typical_cadence_days` must be > 0. Returns HTTP 422 on invalid input.

- **POST /evaluate-renewal**: Compare two subscription plan prices.
  - **Headers:** `Content-Type: application/json`
  - **Body:**
    ```json
    {
      "current_plan_amount": "2400.00",
      "alternate_plan_amount": "2200.00"
    }
    ```
  - **Response:**
    ```json
    {
      "recommended_action": "switch_to_alternate",
      "savings_amount": "200.00"
    }
    ```
  - **Validation:** Both amounts must be > 0. Returns HTTP 422 on invalid input.

## Usage Steps

1. **Step 1 — Health Check:** Send `GET /health` to verify the service is available.
2. **Step 2 — Predict Depletion:** Construct a JSON payload with `last_purchased_at` (ISO 8601 date) and `typical_cadence_days` (positive number). Send `POST /predict-depletion`.
3. **Step 3 — Interpret Result:** Use `predicted_depletion_date` to schedule a reminder. Use `days_until_depletion` to assess urgency (≤ 2 = imminent).
4. **Step 4 — Evaluate Renewal:** Construct a JSON payload with `current_plan_amount` and `alternate_plan_amount` (decimal strings). Send `POST /evaluate-renewal`.
5. **Step 5 — Act on Recommendation:** If `recommended_action` is `switch_to_alternate`, present the savings to the user. Always obtain explicit user approval before changing a plan.

## Security & Best Practices

- **Stateless:** No data is stored. No authentication required.
- **No sensitive data:** Do not send credentials, payment details, user identity, or any PII. The service has no merchant or payment side effects.
- **Rate limits:** Standard Railway platform limits apply.
- **Error handling:** HTTP 422 for validation errors, HTTP 500 for unexpected errors. All error responses include a `detail` field.
