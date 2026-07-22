# Slack delivery and service-auth boundary

Restock Teams notifications use a durable `slack_deliveries` outbox. Creating a
Teams notification and its unique outbox row occurs in one database transaction.
The Slack process claims one pending row with a database lock, passes its delivery
ID as Slack's deterministic `client_msg_id`, and records the returned message
timestamp before another row is claimed.

Delivery is deliberately fail-closed. A network error can occur after Slack accepts
a message, so an ambiguous attempt becomes `failed_ambiguous` and is not retried
automatically. This favors one visible notification over the risk of duplicate
approval messages. Operators reconcile those rows before any manual requeue feature
is introduced.

Slack actions call only
`/api/v1/service/slack/workflows/{run_id}/actions`. That route uses
`RESTOCK_SLACK_SERVICE_TOKEN`, a dedicated constant-time compared credential, and
accepts only Approve, Skip, Renew as-is, or Switch plan. User sessions are not used,
and the service credential is not accepted by the general user API.

When a positive action reaches `passkey_pending`, Slack receives only a link to the
authenticated Restock PWA identified by `RESTOCK_PUBLIC_APP_URL`. The PWA retrieves
the short-lived approval handoff through its authenticated API flow. Raw Prava
iframe/approval URLs are never written to Slack messages or the delivery outbox.
Skip is terminal and renders no continuation link.

The token and all Slack credentials belong only in deployment secret management.
Rotate them independently and rotate any value previously pasted into chat before
deployment.
