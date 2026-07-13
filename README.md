# Restock

Restock is a consumption-triggered replenishment agent that predicts when recurring household essentials will run out, or when team subscriptions will renew, and prepares a bounded Prava payment flow before the deadline.

This repository currently contains pre-hackathon scaffolding and deterministic/stubbed components only. Live Prava and merchant integrations are deliberately deferred to the hackathon window.

## Offline dry run

After installing the project, run `python demo/dry_run.py` to exercise all five seeded items against fake Prava and merchant responses. The Restock Teams billing checkout is an intentional, disclosed simulation.

## Project specifications

- [Product requirements](PRD.md)
- [Technical requirements](TECHNICAL_PRD.md)
- [Build skill and canonical structure](SKILL.md)
