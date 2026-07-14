# Phase 4 Agents SDK Review

Date reviewed: 2026-07-14  
Scope: findings only; no orchestrator, prompt, or test code changed.

## 1. Installed SDK compatibility

The project virtual environment contains `openai-agents 0.18.2`, and `pip check` reports no broken requirements. Runtime introspection confirms that this installed version exposes every SDK API used by `agent/orchestrator.py`: `Agent`, `Runner.run`, `function_tool`, `tool_input_guardrail`, `ToolGuardrailFunctionOutput.allow`, and `ToolGuardrailFunctionOutput.raise_exception`.

In particular, the installed `function_tool` signature includes both `needs_approval` and `tool_input_guardrails`, which are the two Phase 4 features this project relies on. The focused suite also passes with deprecation warnings treated as errors:

```text
pytest tests/test_orchestrator_stubbed.py \
  -W error::DeprecationWarning \
  -W error::PendingDeprecationWarning -q
7 passed
```

No deprecated call is currently evidenced. The main compatibility risk is that `pyproject.toml` specifies an unpinned dependency:

```toml
"openai-agents",
```

A future clean installation can therefore select a newer SDK than the reviewed `0.18.2`. Re-run this review after any dependency upgrade. The current implementation also matches the official Agents SDK descriptions of [function-tool guardrails](https://openai.github.io/openai-agents-python/guardrails/) and [human-in-the-loop approval](https://openai.github.io/openai-agents-python/human_in_the_loop/).

## 2. Spend caps are enforced by a real SDK tool guardrail

The cap policy is not confined to the system prompt. `spend_cap_guardrail` is an SDK `ToolInputGuardrail`:

```python
@tool_input_guardrail(name="spend_cap_guardrail")
def spend_cap_guardrail(data) -> ToolGuardrailFunctionOutput:
    arguments = json.loads(data.context.tool_arguments or "{}")
    try:
        enforce_spend_caps(data.context.context, Decimal(str(arguments["amount"])))
    except (KeyError, SpendCapExceeded) as exc:
        return ToolGuardrailFunctionOutput.raise_exception(
            {"reason": str(exc), "policy": "spend_caps"}
        )
```

It is attached directly to the SDK function tool:

```python
@function_tool(strict_mode=False, tool_input_guardrails=[spend_cap_guardrail])
async def request_prava_intent(...):
```

The underlying code-owned policy checks both required caps, as well as the per-transaction cap:

```python
if amount > context.user.per_item_cap:
    raise SpendCapExceeded(...)

if amount > context.user.per_transaction_cap:
    raise SpendCapExceeded(...)

if context.monthly_spend + amount > context.user.monthly_cap:
    raise SpendCapExceeded(...)
```

The deterministic pre-hackathon path applies the same policy before the stub call:

```python
enforce_spend_caps(context, amount)
...
intent_ref = prava_client.create_intent(merchant, amount, item.name, constraints)
```

`tests/test_orchestrator_stubbed.py` verifies the attached SDK guardrail produces `raise_exception`, and separately monkeypatches `prava_client.create_intent` to prove neither a per-item nor monthly-cap breach reaches the client. The system prompt also describes the limits, but it is not the enforcement mechanism.

## 3. Passkey approval uses the SDK HITL flag

The approval tool is explicitly marked with the SDK's resumable human-in-the-loop primitive:

```python
@function_tool(needs_approval=True)
def await_passkey_approval(...):
```

The focused test confirms the generated tool retains that setting:

```python
def test_approval_tool_uses_sdk_resumable_approval_primitive() -> None:
    assert await_passkey_approval.needs_approval is True
```

This matches the current SDK guidance: a function tool with `needs_approval=True` interrupts the run, which can then be serialized, approved or rejected, and resumed through `RunState`.

## 4. Required six-tool surface

`RESTOCK_AGENT` exposes exactly the six required tools:

```python
tools=[
    check_trigger_status,
    request_prava_intent,
    notify_user,
    await_passkey_approval,
    complete_merchant_checkout,
    log_event,
],
```

Runtime inspection returns these same six tool names; no required tool is missing.

## 5. Stubbed orchestrator tests make no live network calls

`tests/test_orchestrator_stubbed.py` contains no OpenAI or Prava endpoint, HTTP client, socket call, or `Runner.run` invocation. Its full-cycle test calls:

```python
trace = RestockOrchestrator(context).run_cycle(item)
```

`run_cycle` invokes the local deterministic helpers and the Phase 3 fake clients. `payments/prava_client.py` and both merchant implementations used by the test are explicitly offline stubs. The SDK guardrail test calls `spend_cap_guardrail.run(...)` locally; it does not run an agent or model.

The production SDK tools `notify_user` and the Teams branch of `request_prava_intent` do contain `Runner.run(...)` calls, but the stubbed tests do not invoke those tool bodies. All seven focused tests pass without `OPENAI_API_KEY` or `PRAVA_API_KEY`.

## 6. Model configuration

The configured strings are literal constants:

```python
ROUTINE_MODEL = "gpt-5.4-mini"
JUDGMENT_MODEL = "gpt-5.6-sol"
```

They are assigned as specified:

```python
NOTIFICATION_AGENT = Agent(..., model=JUDGMENT_MODEL)
TEAMS_DECISION_AGENT = Agent(..., model=JUDGMENT_MODEL, ...)
RESTOCK_AGENT = Agent(..., model=ROUTINE_MODEL, ...)
```

The test suite asserts the exact strings:

```python
assert RESTOCK_AGENT.model == ROUTINE_MODEL == "gpt-5.4-mini"
assert NOTIFICATION_AGENT.model == JUDGMENT_MODEL == "gpt-5.6-sol"
assert TEAMS_DECISION_AGENT.model == JUDGMENT_MODEL
```

As of this review, the official OpenAI model catalog lists [`gpt-5.4-mini`](https://developers.openai.com/api/docs/models/gpt-5.4-mini) and [`gpt-5.6-sol`](https://developers.openai.com/api/docs/models). This confirms the public model IDs, not access for this particular API project or usage tier. Recheck the official catalog and make one authenticated availability call at hackathon time; do not assume account access from repository configuration alone.

## Conclusion

Phase 4 is compatible with the installed Agents SDK and meets the requested guardrail, approval, tool-surface, model-string, and offline-test requirements. No source-code correction is required by this review. The two operational follow-ups are to pin or deliberately upgrade the SDK before a reproducible release, and to confirm authenticated access to both configured models at hackathon time.
