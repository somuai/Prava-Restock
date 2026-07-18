# Restock

Restock is a consumption-triggered replenishment agent that predicts when recurring household essentials will run out, or when team subscriptions will renew, and prepares a bounded Prava payment flow before the deadline.

The repository contains the deterministic trigger/orchestrator foundation and a real Prava sandbox client. The merchant checkout boundary remains disclosed simulation until Phase 8 completes; see [Phase 7 evidence](docs/phase7_evidence.md) and the real-versus-simulated notes below.

## Offline dry run

After installing the project, run `.venv/bin/python demo/dry_run.py` to exercise all five seeded items in deterministic demo mode. The Restock Teams billing checkout and final Home merchant charge are intentional, disclosed simulations.

## Local API

Run `.venv/bin/uvicorn ui.api:app --reload` and open `/`, `/health`, `/audit-log`, or `/notifications/pending`. The included Dockerfile, `render.yaml`, and `railway.json` can deploy the API without committing credentials.

## Deployment

Hosted URL: [restock-offline-stub-production.up.railway.app](https://restock-offline-stub-production.up.railway.app)

After deployment, verify every public endpoint with:

```bash
./scripts/smoke_test.sh https://restock-offline-stub-production.up.railway.app
```

The currently hosted URL is the credential-free Phase 6 offline deployment. The repository's local Phase 7 integration can call the real Prava sandbox when credentials are supplied through `.env`; those credentials are not committed or baked into the image.

## What is real and what is simulated

- **Real:** deterministic trigger logic, code-owned spend caps, OpenAI Agents SDK tool surface, and Prava sandbox intent/passkey/mandate integration.
- **Disclosed simulation:** final Zepto charge and Restock Teams billing-portal fulfillment until their Phase 8 adapters are enabled.
- **Hosted URL:** still the Phase 6 offline build until the later deployment phase publishes the resumable workflow and UI.

## Project specifications

- [Product requirements](PRD.md)
- [Technical requirements](TECHNICAL_PRD.md)
- [Build skill and canonical structure](SKILL.md)
