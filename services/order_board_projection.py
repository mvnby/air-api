"""Read-only queue projection. Scalar queries deliberately bypass ORM graphs.

Money is computed from scoped scalar line/payment aggregates, never a partial
sum of loaded children or a stale order cache. Every count/page uses the same visibility fence.
"""

from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from sqlalchemy import String, and_, case, cast, false, func, not_, or_, select

from models import Customer, CustomerType, Order, OrderStatus
from services.order_service import OrderService
from services.order_responsibility_service import OrderResponsibilityService
from services.tenant_entity_access_service import TenantEntityAccessService
from services.order_board_money import board_money


class OrderBoardProjection:
    @staticmethod
    def queues():
        live = Order.status.in_([OrderStatus.NEGOTIATION, OrderStatus.EXECUTION])
        return {
            "active": and_(live, Order.is_on_hold.is_(False)),
            "waiting": and_(live, Order.is_on_hold.is_(True)),
            "history": Order.status == OrderStatus.CLOSED,
            "all": or_(live, Order.status == OrderStatus.CLOSED),
        }

    @staticmethod
    def phases():
        negotiation = case(
            (
                Order.negotiation_status.in_(OrderService.NEGOTIATION_STATUSES),
                Order.negotiation_status,
            ),
            (
                Order.status != OrderStatus.NEGOTIATION,
                OrderService.DEFAULT_NEGOTIATION_STATUS,
            ),
            (Order.proposal_status == "sent", "proposal_sent"),
            (
                and_(Order.proposal_status == "approved", Order.is_paid.is_(False)),
                "awaiting_payment",
            ),
            (Order.measurement_required.is_(True), "awaiting_visit"),
            else_=OrderService.DEFAULT_NEGOTIATION_STATUS,
        )
        execution = case(
            (
                Order.execution_status.in_(OrderService.EXECUTION_STATUSES),
                Order.execution_status,
            ),
            (
                Order.status != OrderStatus.EXECUTION,
                OrderService.DEFAULT_EXECUTION_STATUS,
            ),
            (Order.installation_date.is_not(None), "scheduled"),
            else_=OrderService.DEFAULT_EXECUTION_STATUS,
        )
        return negotiation, execution

    @staticmethod
    def work_filters(now):
        _, execution = OrderBoardProjection.phases()
        return {
            "all": ~false(),
            "followup": and_(
                Order.status.in_([OrderStatus.NEGOTIATION, OrderStatus.EXECUTION]),
                Order.next_followup_date <= now,
            ),
            "planning": or_(
                and_(
                    Order.status == OrderStatus.NEGOTIATION,
                    Order.proposal_status == "approved",
                ),
                and_(
                    Order.status == OrderStatus.EXECUTION, execution == "needs_schedule"
                ),
            ),
            "unpaid": Order.balance_due > 0,
        }

    @classmethod
    async def page(
        cls,
        session,
        *,
        tenant_scope,
        segment="b2c",
        queue="active",
        status=None,
        search=None,
        assigned_to_me=False,
        staff_user_id=None,
        customer_id=None,
        work_filter="all",
        result=None,
        closed_from: date | None = None,
        closed_to: date | None = None,
        include_unknown_date=False,
        group_by_customer=False,
        group_key=None,
        phase=None,
        column=None,
        page=1,
        limit=25,
        sort="created_at_desc",
    ):
        queues, work = cls.queues(), cls.work_filters(datetime.now())
        if (
            queue not in queues
            or work_filter not in work
            or segment not in {"all", "b2b", "b2c"}
        ):
            raise ValueError("Invalid queue, segment or work filter")
        if page < 1 or not 1 <= limit <= 100:
            raise ValueError("Invalid page or limit")
        if closed_from and closed_to and closed_from > closed_to:
            raise ValueError("Closing date range is reversed")
        filters = [
            TenantEntityAccessService.order_clause(tenant_scope),
            TenantEntityAccessService.order_customer_clause(tenant_scope),
            queues["all"],
        ]
        b2b = or_(
            cast(Customer.type, String).in_(
                [CustomerType.company.value, CustomerType.individual_entrepreneur.value]
            ),
            and_(Customer.inn.is_not(None), func.length(func.trim(Customer.inn)) > 0),
        )
        if segment == "b2b":
            filters.append(b2b)
        if segment == "b2c":
            filters.append(or_(Customer.id.is_(None), not_(b2b)))
        if assigned_to_me:
            filters.append(
                Order.responsible_staff_user_id == staff_user_id
                if staff_user_id is not None
                else false()
            )
        if customer_id is not None:
            filters.append(Order.customer_id == customer_id)
        if status:
            if status not in {"negotiation", "execution", "closed"}:
                raise ValueError("Invalid status")
            filters.append(Order.status == status)
        if search and search.strip():
            text = search.strip()
            like = f"%{text}%"
            filters.append(
                or_(
                    Customer.name.ilike(like),
                    Customer.phone.ilike(like),
                    Customer.full_legal_name.ilike(like),
                    Customer.inn.ilike(like),
                    Order.title.ilike(like),
                    Order.delivery_address.ilike(like),
                    cast(Order.id, String).ilike(like),
                    *[
                        cast(Order.technical_meta, String).ilike(f"%{v}%")
                        for v in OrderService._json_text_search_variants(text)
                    ],
                )
            )
        if result:
            if result not in {"won", "lost", "unknown"}:
                raise ValueError("Invalid closing result")
            filters.append(
                Order.closing_result.is_(None)
                if result == "unknown"
                else Order.closing_result == result
            )
        dates = []
        if closed_from:
            dates.append(Order.closed_at >= datetime.combine(closed_from, time.min))
        if closed_to:
            dates.append(
                Order.closed_at
                < datetime.combine(closed_to + timedelta(days=1), time.min)
            )
        if dates:
            filters.append(
                or_(and_(*dates), Order.closed_at.is_(None))
                if include_unknown_date
                else and_(*dates)
            )

        money_scope = (
            or_(queues["active"], queues["waiting"])
            if work_filter == "followup"
            else queues[queue]
        )
        visible_ids = (
            select(Order.id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(*filters, money_scope)
            .cte("board_visible_orders")
        )
        money = board_money(visible_ids)
        work["unpaid"] = money.c.balance_due > 0

        def query(*columns, where=filters, with_money=True):
            statement = (
                select(*columns)
                .select_from(Order)
                .outerjoin(Customer, Customer.id == Order.customer_id)
            )
            if with_money:
                statement = statement.join(money, money.c.id == Order.id)
            return statement.where(*where)

        # Queue counters deliberately ignore only the selected queue and work chip.
        counts = (
            (
                await session.execute(
                    query(
                        *[
                            func.count().filter(predicate).label(key)
                            for key, predicate in queues.items()
                        ],
                        with_money=False,
                    )
                )
            )
            .one()
            ._asdict()
        )
        # Due contacts span active + waiting, including when active is selected.
        work_counts = {}
        for key, predicate in work.items():
            scope = (
                or_(queues["active"], queues["waiting"])
                if work_filter == "followup" or key == "followup"
                else queues[queue]
            )
            work_counts[key] = int(
                (
                    await session.execute(
                        query(
                            func.count(),
                            where=[*filters, scope, predicate],
                            with_money=key == "unpaid",
                        )
                    )
                ).scalar_one()
            )
        effective_queue = "all" if work_filter == "followup" else queue
        selected = [*filters, queues[effective_queue], work[work_filter]]
        if column:
            if column not in {"negotiation", "execution"}:
                raise ValueError("Invalid column")
            selected.append(Order.status == column)
        if phase:
            if column not in {"negotiation", "execution"}:
                raise ValueError("Phase requires a live column")
            allowed = (
                OrderService.NEGOTIATION_STATUSES
                if column == "negotiation"
                else OrderService.EXECUTION_STATUSES
            )
            if phase not in allowed:
                raise ValueError("Invalid phase")
            negotiation, execution = cls.phases()
            selected.append(
                (negotiation if column == "negotiation" else execution) == phase
            )
        if group_key:
            try:
                kind, identity = group_key.split(":")
                identity = int(identity)
                if identity <= 0:
                    raise ValueError()
                if kind == "customer":
                    selected.append(Order.customer_id == identity)
                elif kind == "order":
                    selected.extend([Order.customer_id.is_(None), Order.id == identity])
                else:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError("Invalid group key") from None
        sort_map = {
            "created_at_desc": Order.created_at.desc(),
            "created_at_asc": Order.created_at.asc(),
            "updated_at_desc": Order.updated_at.desc().nullslast(),
            "updated_at_asc": Order.updated_at.asc().nullslast(),
            "followup_asc": Order.next_followup_date.asc().nullslast(),
            "followup_desc": Order.next_followup_date.desc().nullslast(),
            "margin_desc": money.c.margin.desc(),
            "margin_asc": money.c.margin.asc(),
            "closed_at_desc": Order.closed_at.desc().nullslast(),
            "closed_at_asc": Order.closed_at.asc().nullslast(),
        }
        if sort not in sort_map:
            raise ValueError("Invalid sort")
        total_orders = int(
            (
                await session.execute(
                    query(
                        func.count(), where=selected, with_money=work_filter == "unpaid"
                    )
                )
            ).scalar_one()
        )
        groups, items = [], []
        if group_by_customer and not group_key:
            identity = case(
                (Order.customer_id.is_not(None), Order.customer_id), else_=-Order.id
            )
            grouped = query(
                identity.label("identity"),
                func.max(Customer.name).label("customer_name"),
                func.count().label("count"),
                func.min(Order.id).label("single_order_id"),
                func.sum(money.c.total_amount).label("total_amount"),
                func.sum(money.c.balance_due).label("balance_due"),
                func.sum(money.c.margin).label("margin"),
                where=selected,
            ).group_by(identity)
            total = int(
                (
                    await session.execute(
                        select(func.count()).select_from(grouped.subquery())
                    )
                ).scalar_one()
            )
            # Aggregate sort is stable and follows the requested metric.
            metric = {
                "created_at": Order.created_at,
                "updated_at": Order.updated_at,
                "followup": Order.next_followup_date,
                "margin": money.c.margin,
                "closed_at": Order.closed_at,
            }
            key, direction = sort.rsplit("_", 1)
            aggregate = (
                func.min(metric[key]) if direction == "asc" else func.max(metric[key])
            )
            ordering = (
                aggregate.asc().nullslast()
                if direction == "asc"
                else aggregate.desc().nullslast()
            )
            rows = (
                await session.execute(
                    grouped.order_by(ordering, identity)
                    .offset((page - 1) * limit)
                    .limit(limit)
                )
            ).mappings()
            for row in rows:
                value = row["identity"]
                groups.append(
                    dict(
                        key=f"customer:{value}" if value > 0 else f"order:{-value}",
                        customer_id=value if value > 0 else None,
                        order_id=row["single_order_id"] if row["count"] == 1 else None,
                        customer_name=row["customer_name"] or "Без клиента",
                        count=row["count"],
                        total_amount=row["total_amount"] or 0,
                        balance_due=row["balance_due"] or 0,
                        margin=None
                        if tenant_scope.demo_read_only
                        else (row["margin"] or 0),
                    )
                )
            singleton_ids = [
                group["order_id"] for group in groups if group["count"] == 1
            ]
            card_filters = [*selected, Order.id.in_(singleton_ids)]
            card_offset = 0
        else:
            total = total_orders
            singleton_ids = None
            card_filters = selected
            card_offset = (page - 1) * limit
        if singleton_ids is None or singleton_ids:
            # Selecting table columns creates Rows, not ORM entities with automatic selectin relationships.
            money_fields = {
                "total_amount",
                "total_cost",
                "margin",
                "total_payments",
                "balance_due",
                "target_currency_payments",
            }
            rows = (
                (
                    await session.execute(
                        query(
                            *[
                                c
                                for c in Order.__table__.c
                                if c.name not in money_fields
                            ],
                            *[c for c in money.c if c.name != "id"],
                            Customer.name.label("customer_name"),
                            Customer.type.label("customer_type"),
                            Customer.phone.label("customer_phone"),
                            Customer.inn.label("customer_inn"),
                            Customer.full_legal_name.label("customer_legal_name"),
                            where=card_filters,
                        )
                        .order_by(sort_map[sort], Order.id.desc())
                        .offset(card_offset)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
            people = await OrderResponsibilityService.person_map(
                session, [SimpleNamespace(**row) for row in rows]
            )
            for row in rows:
                data = dict(row)
                # Preserve the legacy list's read-only defaults for nullable statuses.
                data["equipment_status"] = data["equipment_status"] or "pending"
                data["proposal_status"] = data["proposal_status"] or "draft"
                obj = SimpleNamespace(**data)
                data["manager_labels"] = OrderService._get_manager_labels(obj)
                data["title"] = OrderService._display_order_title(obj)
                data["negotiation_status"] = OrderService._infer_negotiation_status(obj)
                data["execution_status"] = OrderService._infer_execution_status(obj)
                data["customer"] = (
                    dict(
                        id=row["customer_id"],
                        name=row["customer_name"] or "Без имени",
                        type=row["customer_type"],
                        phone=row["customer_phone"] or "",
                        inn=row["customer_inn"],
                        full_legal_name=row["customer_legal_name"],
                    )
                    if row["customer_id"]
                    else None
                )
                data["responsible_person"] = people.get(row["id"])
                if tenant_scope.demo_read_only:
                    data.update(total_cost=None, margin=None, installer_cost_byn=None)
                # Validation selects the public scalar card fields, dropping technical_meta etc.
                from schemas_manager_orders import ManagerOrderListItemResponse

                items.append(ManagerOrderListItemResponse.model_validate(data))
        return dict(
            items=items,
            groups=groups,
            total=total,
            total_orders=total_orders,
            page=page,
            limit=limit,
            has_more=page * limit < total,
            queue_counts=counts,
            work_counts=work_counts,
        )
