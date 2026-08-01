"""Composition root for workflow and explicitly gated merchant dependencies."""

from __future__ import annotations

import os
import json

from merchant import saas_invoice_checkout, zepto_checkout
from merchant.payment_executor import SubprocessBrowserPaymentExecutor
from merchant.health_check import check_merchant_availability
from merchant.quote_provider import build_home_quote_provider
from merchant.quote_provider import build_checkout_context_provider
from merchant.zepto_mcp import ZeptoMCPClient
from storage.repository import RestockRepository
from workflow.service import WorkflowService


def _teams_hosted_link_resolver(reference: str) -> str:
    """Resolve an opaque invoice reference from deployment secret management."""

    try:
        mapping = json.loads(os.getenv("TEAMS_HOSTED_INVOICE_LINKS_JSON", "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("hosted-invoice secret map is invalid") from exc
    if not isinstance(mapping, dict) or not isinstance(mapping.get(reference), str):
        raise KeyError(f"unknown hosted invoice reference: {reference}")
    return str(mapping[reference])


def configure_merchant_runtime(repository: RestockRepository) -> ZeptoMCPClient:
    """Construct the production Zepto runtime without performing network I/O."""

    client = ZeptoMCPClient()
    hosts = tuple(
        host.strip()
        for host in os.getenv("ZEPTO_PAYMENT_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )
    policy = zepto_checkout.PaymentRedirectPolicy(hosts) if hosts else None
    executable = os.getenv("ZEPTO_PAYMENT_EXECUTOR_PATH", "").strip()
    executor = (
        SubprocessBrowserPaymentExecutor(
            executable,
            timeout_seconds=int(os.getenv("ZEPTO_PAYMENT_EXECUTOR_TIMEOUT_SECONDS", "300")),
        )
        if executable
        else None
    )
    zepto_checkout.configure_real_checkout_runtime(
        zepto_checkout.RealCheckoutRuntime(
            repository=repository,
            client=client,
            address_id="",
            merchant_health_check=check_merchant_availability,
            executor=executor,
            redirect_policy=policy,
            checkout_context_provider=build_checkout_context_provider(repository),
        )
    )
    return client


def configure_teams_runtime(repository: RestockRepository) -> None:
    """Compose the independent hosted-invoice payment boundary."""

    teams_hosts = tuple(
        host.strip()
        for host in os.getenv("TEAMS_PAYMENT_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )
    teams_executable = os.getenv("TEAMS_PAYMENT_EXECUTOR_PATH", "").strip()
    teams_executor = (
        SubprocessBrowserPaymentExecutor(
            teams_executable,
            timeout_seconds=int(
                os.getenv("TEAMS_PAYMENT_EXECUTOR_TIMEOUT_SECONDS", "300")
            ),
        )
        if teams_executable
        else None
    )
    saas_invoice_checkout.configure_runtime(
        saas_invoice_checkout.HostedInvoiceRuntime(
            repository=repository,
            executor=teams_executor,
            redirect_policy=zepto_checkout.PaymentRedirectPolicy(teams_hosts),
            link_resolver=_teams_hosted_link_resolver,
        )
        if teams_executor and teams_hosts
        else None
    )


def build_workflow_service(repository: RestockRepository) -> WorkflowService:
    client = configure_merchant_runtime(repository)
    configure_teams_runtime(repository)
    return WorkflowService(
        repository,
        quote_provider=build_home_quote_provider(repository, zepto_client=client),
    )
