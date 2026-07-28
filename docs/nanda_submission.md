# NANDA Town service submission

The standalone **Restock Trigger Math** service is hosted at
<https://restock-trigger-math-production.up.railway.app>. Its agent-facing
instructions are served at
<https://restock-trigger-math-production.up.railway.app/skill.md> and tracked
in [nanda_trigger_service/SKILL.md](../nanda_trigger_service/SKILL.md).

The official Phase 2 format requires a plain Markdown `SKILL.md` containing a
title and one-sentence purpose, base URL, each endpoint with its method/path,
description, example `curl` and example response, followed by numbered agent
usage steps. The official submission mechanism is the form on
<https://nandatown.projectnanda.org/skills>, where the service link, hosted
`SKILL.md`/GitHub URL, and one full public URL per endpoint are supplied.

No NANDA Town submission has been made from this repository. The official
NandaHack deadline displayed on the event site was 11 July 2026; this service
is therefore prepared as a public generic utility, not represented as an
on-time hackathon entry. If the owner chooses to submit it later, first verify
that `/health`, `/predict-depletion`, `/evaluate-renewal`, and `/skill.md`
respond publicly, then use the registry form. Do not submit without the
owner’s explicit confirmation.
