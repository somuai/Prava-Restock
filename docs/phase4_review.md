# Phase 4 Agents SDK Review

Date reviewed: 2026-07-14; model configuration updated: 2026-07-15;
current-state correction: 2026-07-29
Original review scope: findings only; model section later aligned with the implemented single-model decision.

## 1. Installed SDK compatibility

The project virtual environment contains `openai-agents 0.18.2`, and `pip check` reports no broken requirements. Runtime introspection confirms that this installed version exposes every SDK API used by `agent/orchestrator.py`: `Agent`, `Runner.run`, `function_tool`, `tool_input_guardrail`, `ToolGuardrailFunctionOutput.allow`, and `ToolGuardrailFunctionOutput.raise_exception`.

In particular, the installed `function_tool` signature includes both `needs_approval` and `tool_input_guardrails`, which are the two Phase 4 features this project relies on. The focused suite also passes with deprecation warnings treated as errors:

```text
pytest tests/test_orchestrator_stubbed.py \
  -W error::DeprecationWarning \
  -W error::PendingDeprecationWarning -q
7 passed
```

No deprecated call is currently evidenced. The reviewed dependency is now
pinned reproducibly in `pyproject.toml`:

```toml
"openai-agents==0.18.2",
```

A clean installation therefore resolves the same SDK version reviewed here.
Re-run this review after any deliberate dependency upgrade. The current
implementation also matches the official Agents SDK descriptions of
[function-tool guardrails](https://openai.github.io/openai-agents-python/guardrails/)
and [human-in-the-loop approval](https://openai.github.io/openai-agents-python/human_in_the_loop/).

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

The deterministic executor applies the same policy before the Prava client call:

```python
enforce_spend_caps(context, amount)
...
intent_ref = prava_client.create_intent(merchant, amount, item.name, constraints)
```

`tests/test_orchestrator_stubbed.py` verifies the attached SDK guardrail produces
`raise_exception`, and separately monkeypatches `prava_client.create_intent` to
prove neither a per-item nor monthly-cap breach reaches the client. The system
prompt also describes the limits, but it is not the enforcement mechanism.

This review establishes only the completed spend-cap SDK Guardrail. Exact-SKU
substitution refusal, price-deviation reapproval, mandate gating, and
idempotency are deterministic workflow policies and require their own Phase 8
boundary evidence; they are not additional Agents SDK Guardrails.

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

## 5. Deterministic orchestrator tests make no live network calls

`tests/test_orchestrator_stubbed.py` is retained under its historical filename.
It contains no OpenAI or Prava endpoint, HTTP client, socket call, or
`Runner.run` invocation. Its full-cycle test calls:

```python
trace = RestockOrchestrator(context).run_cycle(item)
```

`run_cycle` invokes local deterministic helpers. Tests monkeypatch or inject
payment and merchant boundaries, so the now real-capable
`payments/prava_client.py` cannot make a network call. The SDK guardrail test
calls `spend_cap_guardrail.run(...)` locally; it does not run an agent or model.

The production SDK tools `notify_user` and the Teams branch of `request_prava_intent` do contain `Runner.run(...)` calls, but the stubbed tests do not invoke those tool bodies. All seven focused tests pass without `OPENAI_API_KEY` or `PRAVA_API_KEY`.

## 6. Model configuration

The orchestrator now has one literal model constant:

```python
ORCHESTRATOR_MODEL = "gpt-5.4-mini"
```

It is assigned to every SDK Agent object:

```python
NOTIFICATION_AGENT = Agent(..., model=ORCHESTRATOR_MODEL)
TEAMS_DECISION_AGENT = Agent(..., model=ORCHESTRATOR_MODEL, ...)
RESTOCK_AGENT = Agent(..., model=ORCHESTRATOR_MODEL, ...)
```

The test suite asserts the exact string and all three assignments:

```python
assert ORCHESTRATOR_MODEL == "gpt-5.4-mini"
assert RESTOCK_AGENT.model == ORCHESTRATOR_MODEL
assert NOTIFICATION_AGENT.model == ORCHESTRATOR_MODEL
assert TEAMS_DECISION_AGENT.model == ORCHESTRATOR_MODEL
```

The official OpenAI model catalog lists [`gpt-5.4-mini`](https://developers.openai.com/api/docs/models/gpt-5.4-mini), and the local verifier confirms both listing access and a minimal authenticated invocation for this project account. Using that one verified model for notification copy and Teams comparison as well as the routine loop removes a constrained-quota live-demo dependency; the hard decisions remain bounded by code-level Guardrails and explicit approval.

## Conclusion

Phase 4 is compatible with the pinned Agents SDK and meets the requested
spend-cap guardrail, approval, tool-surface, model-string, and deterministic-test
requirements. Authenticated access to the sole configured model is covered by
the local verifier. Merchant safety policies remain separately evidenced at
their workflow/integration boundaries.
