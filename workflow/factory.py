"""Composition root for workflow and explicitly gated merchant dependencies."""

from __future__ import annotations

import os

from merchant import zepto_checkout
from merchant.payment_executor import SubprocessBrowserPaymentExecutor
from merchant.health_check import check_merchant_availability
from merchant.quote_provider import build_home_quote_provider
from merchant.quote_provider import build_checkout_context_provider
from merchant.zepto_mcp import ZeptoMCPClient
from storage.repository import RestockRepository
from workflow.service import WorkflowService


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


def build_workflow_service(repository: RestockRepository) -> WorkflowService:
    client = configure_merchant_runtime(repository)
    return WorkflowService(
        repository,
        quote_provider=build_home_quote_provider(repository, zepto_client=client),
    )
