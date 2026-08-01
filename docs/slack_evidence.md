# Slack integration evidence

On 22 July 2026, the installed Restock Teams Slack app was exercised against the
configured private workspace without printing or logging credentials.

- Bot authentication succeeded.
- A real Socket Mode connection opened successfully and closed cleanly.
- One clearly labeled, non-transactional smoke notification was delivered to the
  configured Slack destination.
- Approve, Skip, Renew as-is, and Switch plan buttons rendered in that message.
- The Slack message timestamp was `1784735402.162709`.
- Five focused Slack adapter tests passed.

Later the same day, a separate safe callback message was connected to a persisted
test workflow. Its only action was Skip, and the message stated that no payment or
Prava session would be created. The real Socket Mode callback returned HTTP 200 and
changed exactly that workflow from `notified` to `skipped`.

Repeated clicks on an older smoke message also exposed an expected `409` path. The
handler now replaces action buttons with a terminal confirmation after success and
treats an already-processed workflow as idempotent instead of logging it as an
unexpected failure.

The listener is now deployed persistently in the Railway `restock-slack` service
with rotated, non-exposed credentials. Its most recent startup log confirms
`Bolt app is running!`; the service is healthy alongside the API and worker.

The app intentionally holds `chat:write` rather than broader channel-read scopes.
Notification delivery succeeded with that least-privilege scope.
