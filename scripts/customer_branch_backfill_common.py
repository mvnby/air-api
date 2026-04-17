from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, CustomerBranch, Order


_SPACE_RE = re.compile(r"\s+")


@dataclass
class CustomerAddressStat:
    customer_id: int
    customer_name: str
    normalized_address: str
    address_key: str
    order_count: int = 0
    linked_order_count: int = 0
    first_order_at: datetime | None = None
    last_order_at: datetime | None = None


@dataclass
class BranchBackfillPlanItem:
    customer_id: int
    customer_name: str
    delivery_address: str
    address_key: str
    order_count: int
    linked_order_count: int
    is_default: bool


def normalize_address(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _SPACE_RE.sub(" ", value.replace("\n", " ").replace("\r", " ")).strip(" ,;\t")
    return normalized or None


def address_key(value: str | None) -> str | None:
    normalized = normalize_address(value)
    if not normalized:
        return None
    return normalized.casefold()


def _sort_stats(stats: Iterable[CustomerAddressStat]) -> List[CustomerAddressStat]:
    return sorted(
        stats,
        key=lambda item: (
            -item.order_count,
            item.last_order_at or datetime.min,
            item.normalized_address.casefold(),
        ),
    )


def filter_stats_by_min_orders(
    stats_by_customer: Dict[int, List[CustomerAddressStat]],
    min_orders: int,
) -> Dict[int, List[CustomerAddressStat]]:
    min_threshold = max(1, int(min_orders))
    filtered: Dict[int, List[CustomerAddressStat]] = {}
    for customer_id, stats in stats_by_customer.items():
        selected = [item for item in stats if item.order_count >= min_threshold]
        if selected:
            filtered[customer_id] = _sort_stats(selected)
    return filtered


async def fetch_customer_address_stats(session: AsyncSession) -> Dict[int, List[CustomerAddressStat]]:
    stmt = (
        select(
            Order.customer_id,
            Customer.name,
            Order.delivery_address,
            Order.created_at,
            Order.customer_branch_id,
        )
        .join(Customer, Customer.id == Order.customer_id)
        .where(
            Order.customer_id.is_not(None),
            Order.delivery_address.is_not(None),
            func.length(func.trim(Order.delivery_address)) > 0,
        )
        .order_by(Order.customer_id.asc(), Order.created_at.asc(), Order.id.asc())
    )
    rows = (await session.execute(stmt)).all()

    by_customer: Dict[int, Dict[str, CustomerAddressStat]] = {}
    for customer_id_raw, customer_name_raw, delivery_address, created_at, customer_branch_id in rows:
        normalized = normalize_address(delivery_address)
        key = address_key(normalized)
        if not normalized or not key:
            continue

        customer_id = int(customer_id_raw)
        customer_name = str(customer_name_raw or f"Customer #{customer_id}")

        customer_stats = by_customer.setdefault(customer_id, {})
        stat = customer_stats.get(key)
        if stat is None:
            stat = CustomerAddressStat(
                customer_id=customer_id,
                customer_name=customer_name,
                normalized_address=normalized,
                address_key=key,
            )
            customer_stats[key] = stat

        stat.order_count += 1
        if customer_branch_id is not None:
            stat.linked_order_count += 1

        if created_at is not None:
            if stat.first_order_at is None or created_at < stat.first_order_at:
                stat.first_order_at = created_at
            if stat.last_order_at is None or created_at > stat.last_order_at:
                stat.last_order_at = created_at

    result: Dict[int, List[CustomerAddressStat]] = {}
    for customer_id, stats in by_customer.items():
        result[customer_id] = _sort_stats(stats.values())
    return result


async def fetch_existing_branch_keys(session: AsyncSession) -> Dict[int, Dict[str, CustomerBranch]]:
    stmt = (
        select(CustomerBranch)
        .where(CustomerBranch.customer_id.is_not(None))
        .order_by(CustomerBranch.customer_id.asc(), CustomerBranch.created_at.asc(), CustomerBranch.id.asc())
    )
    branches = (await session.execute(stmt)).scalars().all()

    by_customer: Dict[int, Dict[str, CustomerBranch]] = {}
    for branch in branches:
        key = address_key(branch.delivery_address)
        if not key:
            continue
        customer_id = int(branch.customer_id)
        customer_map = by_customer.setdefault(customer_id, {})
        customer_map.setdefault(key, branch)
    return by_customer


def build_backfill_plan(
    *,
    stats_by_customer: Dict[int, List[CustomerAddressStat]],
    existing_branches_by_customer: Dict[int, Dict[str, CustomerBranch]],
) -> List[BranchBackfillPlanItem]:
    plan: List[BranchBackfillPlanItem] = []

    for customer_id in sorted(stats_by_customer.keys()):
        stats = stats_by_customer[customer_id]
        existing_map = dict(existing_branches_by_customer.get(customer_id, {}))
        has_existing_branches = bool(existing_map)
        has_default_branch = any(
            bool(branch.is_default) for branch in existing_branches_by_customer.get(customer_id, {}).values()
        )
        created_for_customer = 0

        for stat in stats:
            if stat.address_key in existing_map:
                continue
            is_default = (not has_existing_branches) and (not has_default_branch) and (created_for_customer == 0)
            plan.append(
                BranchBackfillPlanItem(
                    customer_id=stat.customer_id,
                    customer_name=stat.customer_name,
                    delivery_address=stat.normalized_address,
                    address_key=stat.address_key,
                    order_count=stat.order_count,
                    linked_order_count=stat.linked_order_count,
                    is_default=is_default,
                )
            )
            existing_map[stat.address_key] = CustomerBranch(
                customer_id=stat.customer_id,
                delivery_address=stat.normalized_address,
                is_default=is_default,
            )
            created_for_customer += 1

    return sorted(
        plan,
        key=lambda item: (
            item.customer_name.casefold(),
            item.customer_id,
            -item.order_count,
            item.delivery_address.casefold(),
        ),
    )
