# Railway service configuration

Restock uses three services built from the same repository and Dockerfile. Railway
config-as-code describes one service per file, so set each service's **Config File
Path** to the corresponding absolute repository path:

| Railway service | Config File Path | Public domain |
| --- | --- | --- |
| `restock-api` | `/deploy/railway/api.json` | Yes |
| `restock-worker` | `/deploy/railway/worker.json` | No |
| `restock-slack` | `/deploy/railway/slack.json` | No |

The API alone runs `alembic upgrade head` as its pre-deploy command. Worker and
Slack processes restart until their dependencies become available, avoiding three
concurrent migration runners during a fresh deployment. Keep each process at one
replica initially; the worker still acquires a database lease before scanning. In
particular, keep the API at one replica while Prava's short-lived credential boundary
is process-owned.

## Variable contract

Use Railway references or secret management; never put values in these files.

Shared by API, worker, and Slack:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `RESTOCK_ENV=production`
- `RESTOCK_DEMO_MODE=0`

API only:

- `RESTOCK_SESSION_SECRET`: at least 32 high-entropy characters.
- `RESTOCK_SLACK_SERVICE_TOKEN`: the same independently generated service token
  referenced by the Slack service.
- `RESTOCK_WORKER_SERVICE_TOKEN`: the same independently generated trigger-only
  token referenced by the worker.
- `RESTOCK_ALLOWED_ORIGINS`: the deployed PWA origin when cross-origin access is
  required.
- `PRAVA_API_KEY` paired with `PRAVA_API_URL`. A test key must use
  `https://sandbox.api.prava.space`. A live key must use
  `https://api.prava.space` and also requires `PRAVA_PRODUCTION_ENABLED=1` after
  the separate go-live approval. `PRAVA_SANDBOX_URL` remains a legacy alias for
  the sandbox URL.
- Other provider credentials and execution-mode flags only for integrations
  deliberately activated in that environment.

Worker only:

- `RESTOCK_PUBLIC_API_URL`: the HTTPS API domain.
- `RESTOCK_PUBLIC_APP_URL`: the authenticated PWA URL, normally the API domain
  followed by `/app`.
- `RESTOCK_WORKER_SERVICE_TOKEN`: a high-entropy token accepted only by the
  internal item-trigger route.

The worker never receives Prava credentials and never creates a payment session.
Under its database lease it identifies due item IDs, then asks the API process to
load canonical user/item data and begin the workflow. The database's unique active
workflow constraint suppresses a repeated trigger request, and the API independently
re-checks that the item is active and due before creating the Prava session.

Slack only:

- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `SLACK_SIGNING_SECRET`.
- `SLACK_CHANNEL_ID`: the single destination for this private-workspace release.
- `RESTOCK_PUBLIC_API_URL`: the HTTPS API domain.
- `RESTOCK_SLACK_SERVICE_TOKEN`: a separate high-entropy token accepted only by
  the Slack workflow-action route. It is not a user session and cannot access
  item, audit, approval-URL, resume, or tenant APIs.

Rotate every Slack credential that has appeared in chat before deployment.

Teams notifications use a database outbox with one unique delivery per persisted
notification. A dispatcher atomically claims pending rows before posting. Successful
rows are terminal; network-ambiguous failures are also terminal and require operator
reconciliation, so the process never blind-retries a message that Slack may already
have accepted.

Approve, Renew as-is, and Switch plan callbacks that reach `passkey_pending` replace
the Slack buttons with a link to the authenticated Restock PWA. Slack never receives
or persists the raw Prava iframe/approval URL. Skip remains terminal and has no
continuation link.

Run the same non-secret startup validation locally with:

```bash
python scripts/validate_service_env.py api
python scripts/validate_service_env.py worker
python scripts/validate_service_env.py slack
```

Creating the Postgres, worker, or Slack services is intentionally not automated:
those actions can consume hosting capacity. These files only make their eventual
configuration reproducible.

References: [Railway config as code](https://docs.railway.com/config-as-code),
[custom config paths](https://docs.railway.com/config-as-code#using-a-custom-config-as-code-file),
and [shared-repository services](https://docs.railway.com/deployments/monorepo).
