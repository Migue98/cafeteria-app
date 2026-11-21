"""Recuperación periódica de puntos pendientes."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from traceback import format_exc
from uuid import uuid4

from prometheus_client import Counter, Gauge

from .clients import LoyaltyClient, LoyaltyUnavailable
from .observability import TraceContext, get_logger, log_event
from .repository import OrderRepository, RepositoryUnavailable

LOGGER = get_logger("svc-pedidos.loyalty-retry")

LOYALTY_PENDING = Gauge(
    "cafe_loyalty_pending_orders",
    "Pedidos confirmados cuya acreditación de puntos sigue pendiente.",
)
LOYALTY_RETRIES = Counter(
    "cafe_loyalty_retry_attempts_total",
    "Resultados de los reintentos automáticos de lealtad.",
    ["outcome"],
)


@dataclass(frozen=True, slots=True)
class LoyaltyRetryResult:
    pending_total: int
    attempted: int
    awarded: int
    failed: int


def retry_pending_loyalty(
    repository: OrderRepository,
    loyalty: LoyaltyClient,
    *,
    batch_size: int,
) -> LoyaltyRetryResult:
    orders, pending_total = repository.list_pending_loyalty(limit=batch_size)
    LOYALTY_PENDING.set(pending_total)
    awarded = 0
    failed = 0

    for order in orders:
        request_id = str(uuid4())
        context = TraceContext.from_header()
        try:
            points = loyalty.award(
                order,
                request_id=request_id,
                traceparent=context.traceparent,
            )
            repository.mark_loyalty_awarded(order.id, points)
        except LoyaltyUnavailable as exc:
            failed += 1
            LOYALTY_RETRIES.labels(outcome="loyalty_unavailable").inc()
            log_event(
                LOGGER,
                "loyalty_retry_failed",
                level=logging.WARNING,
                order_id=str(order.id),
                request_id=request_id,
                context=context,
                reason=str(exc),
            )
        except RepositoryUnavailable as exc:
            failed += 1
            LOYALTY_RETRIES.labels(outcome="repository_unavailable").inc()
            log_event(
                LOGGER,
                "loyalty_retry_failed",
                level=logging.ERROR,
                order_id=str(order.id),
                request_id=request_id,
                context=context,
                reason=str(exc),
            )
        else:
            awarded += 1
            LOYALTY_RETRIES.labels(outcome="awarded").inc()
            log_event(
                LOGGER,
                "loyalty_retry_awarded",
                level=logging.INFO,
                order_id=str(order.id),
                points_earned=points,
                request_id=request_id,
                context=context,
            )

    LOYALTY_PENDING.set(max(pending_total - awarded, 0))
    return LoyaltyRetryResult(
        pending_total=pending_total,
        attempted=len(orders),
        awarded=awarded,
        failed=failed,
    )


async def loyalty_retry_loop(
    repository: OrderRepository,
    loyalty: LoyaltyClient,
    *,
    interval_seconds: float,
    batch_size: int,
) -> None:
    while True:
        try:
            result = await asyncio.to_thread(
                retry_pending_loyalty,
                repository,
                loyalty,
                batch_size=batch_size,
            )
            if result.attempted:
                log_event(
                    LOGGER,
                    "loyalty_retry_batch_completed",
                    level=logging.INFO,
                    pending_total=result.pending_total,
                    attempted=result.attempted,
                    awarded=result.awarded,
                    failed=result.failed,
                )
        except RepositoryUnavailable as exc:
            log_event(
                LOGGER,
                "loyalty_retry_batch_failed",
                level=logging.ERROR,
                reason=str(exc),
            )
        except Exception:
            log_event(
                LOGGER,
                "loyalty_retry_batch_failed",
                level=logging.ERROR,
                exception=format_exc(),
            )

        await asyncio.sleep(interval_seconds)
