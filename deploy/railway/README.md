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
- `RESTOCK_SOLO_USER_ID`: the existing owner user UUID represented by the login.
  The user row must already exist in the production database before login is enabled.
- `RESTOCK_SOLO_PASSWORD_HASH`: a scrypt hash produced interactively by
  `scripts/generate_solo_password_hash.py`; never store or deploy the plaintext.
- `RESTOCK_SESSION_TTL_SECONDS=3600` and
  `RESTOCK_AUTH_RATE_LIMIT_PER_MINUTE=5` are safe defaults for the solo login.
  Production login throttling is stored in PostgreSQL and shared across API
  replicas; the API fails closed if that durable throttle is unavailable.
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
- `HOME_MERCHANT_MODE=real` enables real Zepto catalog/cart/quote calls without
  enabling payment. Keep `HOME_PAYMENT_MODE=disclosed_mock` until the controlled
  live-money boundary is ready. Real payment additionally requires
  `HOME_PAYMENT_MODE=real`, `ZEPTO_REAL_PAYMENT_ENABLED=1`, an exact
  `ZEPTO_PAYMENT_ALLOWED_HOSTS` list observed and approved by the operator, and
  an absolute reviewed `ZEPTO_PAYMENT_EXECUTOR_PATH`. The executor receives the
  consume-once fields only over stdin and must return sanitized JSON.
- `ZEPTO_DEVICE_ID` is runtime-only; tracked items persist only an opaque saved
  address reference. `ZEPTO_ADDRESS_ID` is retained solely for the explicit
  local integration harness and is not the production workflow source.

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

The production image includes the Node.js 24 runtime and installs the Zepto
bridge's `mcp-remote@0.1.38` dependency at image-build time from a committed npm
lockfile with integrity hashes. Runtime calls execute that image-local binary and
never download code through npm/npx; CI verifies it in a container with networking
disabled. This makes the executable reproducible, but it does not provision Zepto
authorization. `mcp-remote` stores OAuth state in
`MCP_REMOTE_CONFIG_DIR` (defaulted by the image to `/home/restock/.mcp-auth`). The
zero-added-cost deployment path stores a minimal three-file OAuth bundle in Railway's
encrypted `ZEPTO_MCP_AUTH_CACHE_B64` runtime variable. Sealing it in the Railway UI
is recommended as additional protection because sealed values cannot be retrieved. The container
validates filenames and size, materializes the files with private permissions before
startup, and removes the bundle from the API process environment. Never copy the
cache into the image, repository, database, or logs. A persistent
volume mounted at this path remains an optional alternative, not a requirement.
`MCP_REMOTE_BINARY` must remain unset in production: the image rejects any
override of its integrity-locked `/opt/zepto-mcp/node_modules/.bin/mcp-remote`.
The public capability response labels cache presence `configured_unverified`.
Only a successful MCP initialize/tool call in the current process produces the
short-lived `verified_recently` state required for real-money readiness; it
expires after `MCP_AUTHORIZATION_VERIFICATION_TTL_SECONDS` (300 seconds by
default) and is cleared by a later bridge, authorization, or provider-call
failure.

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
