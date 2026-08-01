# Prava reviewer walkthrough

This walkthrough is for the temporary, isolated reviewer account shared
privately with Prava. It is **not** a public sign-up or an owner account.

1. Open the deployed Restock application and expand **Prava reviewer access**.
2. Enter the privately supplied reviewer password and choose **Open reviewer
   pantry**. The review account contains five low-cap seeded items across Home
   and Teams.
3. In Home, open Coffee and choose **Approve ₹380** to create a Prava sandbox
   approval session. No real-money checkout is enabled in this environment.
4. In Teams, inspect the explicit renew-versus-switch proposal. A plan switch
   always requires its own explicit action.
5. Open Activity to inspect the sanitized, mode-tagged audit trail.

## Current sandbox limitation

Restock successfully creates the hosted Prava sandbox session. The assigned
test card then reaches Prava's security step but currently returns **Security
Check Failed**; on retry it is labelled **No Passkey**, leaving card selection
disabled. This is recorded as a provider-side sandbox/passkey-provisioning
blocker, not an end-to-end success claim. No live purchase is attempted.

Fresh Google sign-in is also available. It creates a new Restock account and
shows the first-run starter-pantry onboarding, rather than exposing the
reviewer's seeded fixtures. If someone chose **Start empty**, the empty pantry
keeps an **Add pantry items** control so the starter selection can be reopened.
