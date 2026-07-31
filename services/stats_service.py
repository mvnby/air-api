from datetime import datetime, timedelta
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.order import BankReceipt, Order
from models.customer import Customer, CustomerContract
from models.common import OrderStatus
from models.tenancy import TenantScope
from schemas import DashboardBankReceiptReviewItem, DashboardContractExpiry, DashboardStatsResponse, DashboardTouchpoint
from services.tenant_scope_service import (
    tenant_scope_clause,
)

class StatsService:
    @staticmethod
    async def get_dashboard_stats(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> DashboardStatsResponse:
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)
        order_scope = tenant_scope_clause(Order, tenant_scope)
        order_customer_scope = or_(
            Order.customer_id.is_(None),
            tenant_scope_clause(Customer, tenant_scope),
        )

        # 1. Total Amount for CLOSED deals in the current month
        total_stmt = (
            select(func.sum(Order.total_amount))
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                order_scope,
                order_customer_scope,
                Order.status == OrderStatus.CLOSED,
                Order.created_at >= start_of_month,
            )
        )
        total_result = await session.execute(total_stmt)
        total_amount = total_result.scalar() or 0.0

        # 2. New Leads count in the current month
        leads_stmt = (
            select(func.count(Order.id))
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                order_scope,
                order_customer_scope,
                Order.status == OrderStatus.NEW_LEAD,
                Order.created_at >= start_of_month,
            )
        )
        leads_result = await session.execute(leads_stmt)
        new_leads_count = leads_result.scalar() or 0

        # 3. Upcoming Touchpoints
        # Find orders with next_followup_date <= 7 days from now, not in closed statuses
        end_of_window = now + timedelta(days=7)
        
        touchpoints_stmt = (
            select(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .options(selectinload(Order.customer))
            .where(
                order_scope,
                order_customer_scope,
                Order.next_followup_date.is_not(None),
                Order.next_followup_date <= end_of_window,
                Order.status != OrderStatus.CLOSED
            )
            .order_by(Order.next_followup_date.asc())
            .limit(5)
        )
        touchpoints_result = await session.execute(touchpoints_stmt)
        orders = touchpoints_result.scalars().all()

        touchpoints = []
        for order in orders:
            customer_name = order.customer.name if order.customer else "Неизвестный клиент"
            phone = order.customer.phone if order.customer else None
            
            touchpoints.append(
                DashboardTouchpoint(
                    order_id=order.id,
                    customer_name=customer_name,
                    phone=phone,
                    next_followup_date=order.next_followup_date,
                    title=order.title
                )
            )

        contracts_stmt = (
            select(CustomerContract)
            .join(Customer, Customer.id == CustomerContract.customer_id)
            .options(selectinload(CustomerContract.customer))
            .where(
                tenant_scope_clause(Customer, tenant_scope),
                CustomerContract.status == "active",
                CustomerContract.valid_until <= end_of_window,
            )
            .order_by(CustomerContract.valid_until.asc())
            .limit(10)
        )
        contracts_result = await session.execute(contracts_stmt)
        contracts = contracts_result.scalars().all()
        expiring_contracts = [
            DashboardContractExpiry(
                contract_id=int(contract.id or 0),
                customer_id=int(contract.customer_id),
                customer_name=contract.customer.name if contract.customer else f"Клиент #{contract.customer_id}",
                number=contract.number,
                valid_until=contract.valid_until,
                edit_url=contract.google_edit_url,
            )
            for contract in contracts
        ]

        bank_receipts_review = []
        bank_receipts_count = 0
        if tenant_scope.is_system:
            bank_receipts_count_stmt = select(func.count(BankReceipt.id)).where(
                BankReceipt.status == "requires_review"
            )
            bank_receipts_count = int(
                (await session.execute(bank_receipts_count_stmt)).scalar() or 0
            )
            bank_receipts_stmt = (
                select(BankReceipt)
                .where(BankReceipt.status == "requires_review")
                .order_by(
                    BankReceipt.received_at.desc().nullslast(),
                    BankReceipt.created_at.desc(),
                )
                .limit(5)
            )
            bank_receipts_result = await session.execute(bank_receipts_stmt)
            for receipt in bank_receipts_result.scalars().all():
                meta = receipt.match_meta if isinstance(receipt.match_meta, dict) else {}
                raw_ids = meta.get("candidate_order_ids") or []
                candidate_order_ids = [int(item) for item in raw_ids if item]
                bank_receipts_review.append(
                    DashboardBankReceiptReviewItem(
                        id=int(receipt.id or 0),
                        received_at=receipt.received_at,
                        amount=float(receipt.amount or 0),
                        currency=receipt.currency,
                        payer_name=receipt.payer_name,
                        payer_unp=receipt.payer_unp,
                        payment_document_number=receipt.payment_document_number,
                        payment_purpose=receipt.payment_purpose,
                        candidate_order_ids=candidate_order_ids,
                    )
                )

        return DashboardStatsResponse(
            total_amount=float(total_amount),
            new_leads_count=new_leads_count,
            upcoming_touchpoints=touchpoints,
            expiring_contracts=expiring_contracts,
            bank_receipts_review_count=bank_receipts_count,
            bank_receipts_review=bank_receipts_review,
        )
