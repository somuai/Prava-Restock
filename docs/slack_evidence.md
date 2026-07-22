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

No action button was clicked because the smoke message intentionally had no real
workflow or transaction behind it. The remaining channel proof is to run the Slack
listener persistently in the deployed environment, create a genuine pending workflow,
and verify that one button callback changes only that workflow.

The app intentionally holds `chat:write` rather than broader channel-read scopes.
Notification delivery succeeded with that least-privilege scope.
