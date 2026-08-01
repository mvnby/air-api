from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import html
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, Order, OrderDocument, Payment
from models.tenancy import TenantScope
from services.documents.base import DOC_NAMES
from services.google_service import get_google_service
from services.settings_service import SettingsService
from services.tenant_scope_service import (
    storefront_scope_clause,
    tenant_scope_clause,
)


DELIVERY_DOC_TYPES = {
    "act",
    "tn2",
    "ttn1",
    "retail_receipt",
    "service_act",
    "maintenance_service_act",
}


@dataclass(frozen=True)
class _Period:
    date_from: date
    date_to: date
    start: datetime
    end: datetime


class CustomerReconciliationService:
    DEFAULT_COMPANY_NAME = "ИП Янулевич Д.В."
    COMPANY_SETTING_DEFAULTS = {
        "company_name": DEFAULT_COMPANY_NAME,
        "company_full_legal_name": DEFAULT_COMPANY_NAME,
        "company_unp": "",
        "company_legal_address": "",
        "company_bank_name": "",
        "company_iban": "",
        "company_bic": "",
        "company_signer_position": "",
        "company_signer_name": "Янулевич Д.В.",
        "company_acting_basis": "",
    }

    @staticmethod
    def _period(date_from: Optional[date], date_to: Optional[date]) -> _Period:
        today = date.today()
        start_date = date_from or date(today.year, 1, 1)
        end_date = date_to or today
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        return _Period(
            date_from=start_date,
            date_to=end_date,
            start=datetime.combine(start_date, time.min),
            end=datetime.combine(end_date, time.max),
        )

    @staticmethod
    def _money(value: Optional[float]) -> float:
        return round(float(value or 0), 2)

    @staticmethod
    def _doc_label(doc: OrderDocument) -> str:
        doc_name = DOC_NAMES.get(doc.doc_type, doc.doc_type.upper())
        return f"{doc_name} №{doc.number}"

    @classmethod
    def _order_date(cls, order: Order, delivery_docs: Iterable[OrderDocument]) -> datetime:
        docs = sorted(delivery_docs, key=lambda item: item.date or item.created_at or datetime.min)
        if docs:
            return docs[0].date
        return order.closed_at or order.contract_date or order.created_at

    @classmethod
    def _order_basis_docs(cls, delivery_docs: Iterable[OrderDocument]) -> list[Dict[str, Any]]:
        return [
            {
                "id": doc.id,
                "doc_type": doc.doc_type,
                "doc_type_label": DOC_NAMES.get(doc.doc_type, doc.doc_type.upper()),
                "number": doc.number,
                "date": doc.date,
                "edit_url": doc.google_edit_url,
            }
            for doc in sorted(delivery_docs, key=lambda item: (item.date, item.id or 0))
        ]

    @staticmethod
    def _payment_payload(
        payment: Payment,
        order: Order,
        *,
        amount_override: Optional[float] = None,
        allocated_amount: Optional[float] = None,
    ) -> Dict[str, Any]:
        receipt = payment.bank_receipt
        return {
            "payment_id": payment.id,
            "order_id": order.id,
            "order_title": order.title or f"Заказ #{order.id}",
            "date": payment.date,
            "amount": CustomerReconciliationService._money(
                payment.amount if amount_override is None else amount_override
            ),
            "allocated_amount": CustomerReconciliationService._money(
                payment.amount if allocated_amount is None else allocated_amount
            ),
            "currency": payment.currency,
            "payment_type": payment.type,
            "comment": payment.comment,
            "bank_receipt_id": receipt.id if receipt else None,
            "payer_name": receipt.payer_name if receipt else None,
            "payer_unp": receipt.payer_unp if receipt else None,
            "payer_account": receipt.payer_account if receipt else None,
            "our_account": receipt.our_account if receipt else None,
            "payment_document_number": receipt.payment_document_number if receipt else None,
            "payment_document_raw": receipt.payment_document_raw if receipt else None,
            "payment_purpose": receipt.payment_purpose if receipt else None,
        }

    @staticmethod
    def _format_date(value: date | datetime | str | None) -> str:
        if not value:
            return "-"
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.strftime("%d.%m.%Y")
            except ValueError:
                return value
        if isinstance(value, datetime):
            return value.strftime("%d.%m.%Y")
        return value.strftime("%d.%m.%Y")

    @staticmethod
    def _format_money(value: float | int | None) -> str:
        amount = float(value or 0)
        return f"{amount:,.2f}".replace(",", " ").replace(".", ",")

    @staticmethod
    def _customer_title(customer: Customer) -> str:
        return (customer.full_legal_name or customer.name or f"Клиент #{customer.id}").strip()

    @classmethod
    async def _company_requisites(cls, session: AsyncSession) -> Dict[str, str]:
        requisites: Dict[str, str] = {}
        for key, default in cls.COMPANY_SETTING_DEFAULTS.items():
            requisites[key] = (
                await SettingsService.get_optional_value(session, key, default)
            ).strip()
        if not requisites.get("company_full_legal_name"):
            requisites["company_full_legal_name"] = requisites.get("company_name") or cls.DEFAULT_COMPANY_NAME
        if not requisites.get("company_name"):
            requisites["company_name"] = requisites.get("company_full_legal_name") or cls.DEFAULT_COMPANY_NAME
        return requisites

    @classmethod
    def _customer_requisites(cls, customer: Customer) -> str:
        parts = [
            cls._customer_title(customer),
            f"УНП {customer.inn}" if customer.inn else "",
            customer.legal_address or customer.actual_address or "",
            customer.iban or "",
            customer.bank_name or "",
            f"BIC {customer.bic}" if customer.bic else "",
        ]
        return ", ".join(part for part in parts if part)

    @classmethod
    def _our_requisites_label(cls, requisites: Dict[str, str]) -> str:
        parts = [
            requisites.get("company_full_legal_name") or requisites.get("company_name") or cls.DEFAULT_COMPANY_NAME,
            f"УНП {requisites.get('company_unp')}" if requisites.get("company_unp") else "",
            requisites.get("company_legal_address") or "",
            requisites.get("company_iban") or "",
            requisites.get("company_bank_name") or "",
            f"BIC {requisites.get('company_bic')}" if requisites.get("company_bic") else "",
        ]
        return ", ".join(part for part in parts if part)

    @staticmethod
    def _payment_label(payment: Dict[str, Any]) -> str:
        if payment.get("payment_document_raw"):
            return str(payment["payment_document_raw"])
        if payment.get("payment_document_number"):
            return f"Платежное поручение №{payment['payment_document_number']}"
        if payment.get("bank_receipt_id"):
            return f"Банковская выписка #{payment['bank_receipt_id']}"
        return f"Платеж #{payment.get('payment_id')}"

    @classmethod
    def _balance_summary(cls, closing_balance: float, company_name: str) -> str:
        amount = cls._format_money(abs(closing_balance))
        if closing_balance > 0:
            return f"Задолженность в пользу {company_name} составляет {amount} BYN."
        if closing_balance < 0:
            return f"Задолженность в пользу контрагента составляет {amount} BYN."
        return "Задолженность между сторонами отсутствует."

    @classmethod
    def _append_movement_row(
        cls,
        rows: list[str],
        index: int,
        row_date: Any,
        document: str,
        operation: str,
        debit: float = 0.0,
        credit: float = 0.0,
    ) -> None:
        rows.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{html.escape(cls._format_date(row_date))}</td>"
            f"<td>{html.escape(document)}</td>"
            f"<td>{html.escape(operation)}</td>"
            f"<td class=\"money\">{cls._format_money(debit) if debit else ''}</td>"
            f"<td class=\"money\">{cls._format_money(credit) if credit else ''}</td>"
            "</tr>"
        )

    @classmethod
    def _build_html_document(cls, customer: Customer, data: Dict[str, Any], company_requisites: Dict[str, str]) -> str:
        rows: list[str] = []
        row_number = 1
        opening = float(data.get("opening_balance") or 0)
        if opening:
            cls._append_movement_row(
                rows,
                row_number,
                data.get("date_from"),
                "Сальдо на начало периода",
                "Входящее сальдо",
                debit=opening if opening > 0 else 0,
                credit=abs(opening) if opening < 0 else 0,
            )
            row_number += 1

        movements: list[tuple[datetime, str, Dict[str, Any]]] = []
        for item in data.get("documents") or []:
            movements.append((item["date"], "document", item))
        for item in data.get("payments") or []:
            movements.append((item["date"], "payment", item))
        movements.sort(key=lambda item: (item[0], item[1], item[2].get("order_id") or 0))

        for _, movement_type, item in movements:
            if movement_type == "document":
                cls._append_movement_row(
                    rows,
                    row_number,
                    item.get("date"),
                    item.get("basis") or f"Заказ #{item.get('order_id')}",
                    item.get("order_title") or f"Заказ #{item.get('order_id')}",
                    debit=float(item.get("amount") or 0),
                )
            else:
                cls._append_movement_row(
                    rows,
                    row_number,
                    item.get("date"),
                    cls._payment_label(item),
                    item.get("payment_purpose") or item.get("comment") or item.get("order_title") or "Оплата",
                    credit=float(item.get("amount") or 0),
                )
            row_number += 1

        if not rows:
            rows.append('<tr><td colspan="6" class="empty">Движений за период нет</td></tr>')

        customer_title = cls._customer_title(customer)
        company_title = company_requisites.get("company_full_legal_name") or company_requisites.get("company_name") or cls.DEFAULT_COMPANY_NAME
        period = f"{cls._format_date(data.get('date_from'))} - {cls._format_date(data.get('date_to'))}"
        summary = cls._balance_summary(float(data.get("closing_balance") or 0), company_title)
        html_rows = "\n".join(rows)
        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 10pt; color: #111827; }}
    h1 {{ font-size: 16pt; text-align: center; margin: 0 0 14pt; }}
    p {{ margin: 0 0 8pt; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12pt; }}
    th, td {{ border: 1px solid #111827; padding: 5pt; vertical-align: top; }}
    th {{ background: #f3f4f6; text-align: center; }}
    .money {{ text-align: right; white-space: nowrap; }}
    .summary {{ margin-top: 12pt; font-weight: bold; }}
    .signatures td {{ height: 48pt; border: none; border-top: 1px solid #111827; padding-top: 6pt; }}
    .empty {{ text-align: center; color: #6b7280; }}
  </style>
</head>
<body>
  <h1>Акт сверки взаимных расчетов</h1>
  <p><strong>Период:</strong> {html.escape(period)}</p>
  <p><strong>Сторона 1:</strong> {html.escape(cls._our_requisites_label(company_requisites))}</p>
  <p><strong>Сторона 2:</strong> {html.escape(cls._customer_requisites(customer))}</p>
  <p>Стороны произвели сверку взаимных расчетов за указанный период и установили следующее:</p>
  <table>
    <thead>
      <tr>
        <th style="width: 5%;">№</th>
        <th style="width: 12%;">Дата</th>
        <th style="width: 25%;">Документ</th>
        <th>Операция</th>
        <th style="width: 14%;">Дебет, BYN</th>
        <th style="width: 14%;">Кредит, BYN</th>
      </tr>
    </thead>
    <tbody>
      {html_rows}
    </tbody>
    <tfoot>
      <tr>
        <th colspan="4">Итого за период</th>
        <th class="money">{cls._format_money(data.get("documents_total"))}</th>
        <th class="money">{cls._format_money(data.get("payments_total"))}</th>
      </tr>
      <tr>
        <th colspan="4">Сальдо на конец периода</th>
        <th colspan="2" class="money">{cls._format_money(abs(float(data.get("closing_balance") or 0)))} BYN</th>
      </tr>
    </tfoot>
  </table>
  <p class="summary">{html.escape(summary)}</p>
  <p>Акт составлен в двух экземплярах, по одному для каждой из сторон.</p>
  <table class="signatures">
    <tr>
      <td style="width: 48%;">От {html.escape(company_title)}<br>Подпись ___________________</td>
      <td style="width: 4%;"></td>
      <td style="width: 48%;">От {html.escape(customer_title)}<br>Подпись ___________________</td>
    </tr>
  </table>
</body>
</html>"""

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        customer_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = (
            await session.execute(
                select(Customer).where(
                    Customer.id == customer_id,
                    tenant_scope_clause(Customer, tenant_scope),
                )
            )
        ).scalars().first()
        if not customer:
            return None

        period = cls._period(date_from, date_to)
        query = (
            select(Order)
            .where(
                Order.customer_id == customer_id,
                storefront_scope_clause(Order, tenant_scope),
            )
            .options(
                selectinload(Order.documents),
                selectinload(Order.payments).selectinload(Payment.bank_receipt),
            )
            .order_by(Order.created_at.asc(), Order.id.asc())
            .execution_options(populate_existing=True)
        )
        result = await session.execute(query)
        orders = list(result.unique().scalars().all())

        opening_documents_total = 0.0
        opening_payments_total = 0.0
        documents_total = 0.0
        payments_total = 0.0
        document_rows: list[Dict[str, Any]] = []
        payment_rows: list[Dict[str, Any]] = []
        seen_bank_receipt_ids: set[int] = set()
        allocated_by_bank_receipt: dict[int, float] = {}
        for order in orders:
            for payment in order.payments:
                if not payment.bank_receipt_id:
                    continue
                receipt_id = int(payment.bank_receipt_id)
                allocated_by_bank_receipt[receipt_id] = cls._money(
                    allocated_by_bank_receipt.get(receipt_id, 0) + payment.amount
                )

        for order in orders:
            delivery_docs = [doc for doc in order.documents if doc.doc_type in DELIVERY_DOC_TYPES]
            order_date = cls._order_date(order, delivery_docs)
            order_amount = cls._money(order.total_amount)

            if order_amount > 0:
                if order_date < period.start:
                    opening_documents_total += order_amount
                elif order_date <= period.end:
                    documents_total += order_amount
                    document_rows.append(
                        {
                            "order_id": order.id,
                            "order_title": order.title or f"Заказ #{order.id}",
                            "date": order_date,
                            "amount": order_amount,
                            "basis": ", ".join(cls._doc_label(doc) for doc in delivery_docs) or f"Заказ #{order.id}",
                            "delivery_address": order.delivery_address,
                            "documents": cls._order_basis_docs(delivery_docs),
                        }
                    )

            for payment in order.payments:
                receipt = payment.bank_receipt
                if receipt and receipt.id:
                    receipt_id = int(receipt.id)
                    if receipt_id in seen_bank_receipt_ids:
                        continue
                    seen_bank_receipt_ids.add(receipt_id)
                    amount = cls._money(receipt.amount)
                    allocated_amount = allocated_by_bank_receipt.get(receipt_id, 0.0)
                else:
                    amount = cls._money(payment.amount)
                    allocated_amount = amount
                if amount <= 0:
                    continue
                if payment.date < period.start:
                    opening_payments_total += amount
                elif payment.date <= period.end:
                    payments_total += amount
                    payment_rows.append(
                        cls._payment_payload(
                            payment,
                            order,
                            amount_override=amount,
                            allocated_amount=allocated_amount,
                        )
                    )

        opening_balance = cls._money(opening_documents_total - opening_payments_total)
        documents_total = cls._money(documents_total)
        payments_total = cls._money(payments_total)
        closing_balance = cls._money(opening_balance + documents_total - payments_total)

        return {
            "customer_id": customer_id,
            "date_from": period.date_from,
            "date_to": period.date_to,
            "opening_balance": opening_balance,
            "documents_total": documents_total,
            "payments_total": payments_total,
            "closing_balance": closing_balance,
            "documents": sorted(document_rows, key=lambda item: (item["date"], item["order_id"])),
            "payments": sorted(payment_rows, key=lambda item: (item["date"], item["payment_id"] or 0)),
        }

    @classmethod
    async def generate_google_doc(
        cls,
        session: AsyncSession,
        customer_id: int,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = (
            await session.execute(
                select(Customer).where(
                    Customer.id == customer_id,
                    tenant_scope_clause(Customer, tenant_scope),
                )
            )
        ).scalars().first()
        if not customer:
            return None
        data = await cls.build(
            session,
            customer_id,
            date_from=date_from,
            date_to=date_to,
            tenant_scope=tenant_scope,
        )
        if data is None:
            return None
        company_requisites = await cls._company_requisites(session)
        period = f"{cls._format_date(data['date_from'])}-{cls._format_date(data['date_to'])}"
        title = f"Акт сверки {cls._customer_title(customer)} {period}"
        file_info = get_google_service().create_document_from_html(title, cls._build_html_document(customer, data, company_requisites))
        return {
            "file_id": file_info["file_id"],
            "edit_url": file_info["edit_url"],
            "title": title,
        }
