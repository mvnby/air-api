from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import BigInteger, Column, JSON, String
from sqlmodel import Field, Relationship, SQLModel

from .common import ClosingResult, DocumentRoleType, EquipmentStatus, LeadSource, OrderStageStatus, OrderStatus, PaymentCurrency, PaymentType

class Installer(SQLModel, table=True):
    __tablename__ = "installers"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    is_active: bool = Field(default=True)
    default_rate: Optional[float] = Field(default=None)

    telegram_id: Optional[int] = Field(default=None, sa_column=Column(BigInteger, unique=True, nullable=True))


class OrderInstaller(SQLModel, table=True):
    __tablename__ = "order_installers"

    order_id: int = Field(foreign_key="order.id", primary_key=True)
    installer_id: int = Field(foreign_key="installers.id", primary_key=True)

    role: str = Field(default="main")
    agreed_pay: float = Field(default=0.0)
    is_paid_to_installer: bool = Field(default=False)

    order: "Order" = Relationship(back_populates="installers")
    installer: "Installer" = Relationship()


class Service(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    category: str = Field(default="installation_option", index=True)
    is_active: bool = Field(default=True)
    image: Optional[str] = None
    description: Optional[str] = None
    base_price: int = Field(default=0)

    order_links: List["OrderServiceLink"] = Relationship(back_populates="service")

    @property
    def image_file(self) -> Any:
        return getattr(self, "_temp_image_file", None)

    @image_file.setter
    def image_file(self, value: Any):
        self._temp_image_file = value

    def __str__(self):
        return f"{self.title} ({self.base_price} руб.)"


class ServiceTariff(SQLModel, table=True):
    __tablename__ = "service_tariff"

    id: Optional[int] = Field(default=None, primary_key=True)
    service_kind: str = Field(default="installation", index=True)
    selector_label: str = Field(index=True)
    estimate_template: str = Field(default="Монтаж кондиционера, включая расходные материалы")
    category: str = Field(default="", index=True)
    power_range: str = Field(default="", index=True)

    base_price: int = Field(default=0)
    included_route_meters: float = Field(default=3.0)

    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    comment: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    rules: List["ServiceTariffRule"] = Relationship(
        back_populates="tariff",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


class ServiceTariffRule(SQLModel, table=True):
    __tablename__ = "service_tariff_rule"

    id: Optional[int] = Field(default=None, primary_key=True)
    tariff_id: int = Field(foreign_key="service_tariff.id", index=True)

    rule_type: str = Field(default="per_unit_manual", index=True)
    name: str = Field(index=True)
    line_template: str = Field(default="{name}")
    unit: str = Field(default="шт")
    unit_price: float = Field(default=0.0)

    is_optional: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    service_id: Optional[int] = Field(default=None, foreign_key="service.id", index=True)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    tariff: "ServiceTariff" = Relationship(back_populates="rules")
    service: Optional["Service"] = Relationship()


class ServiceEstimate(SQLModel, table=True):
    __tablename__ = "service_estimate"
    id: Optional[int] = Field(default=None, primary_key=True)

    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id", index=True)
    tariff_id: Optional[int] = Field(default=None, foreign_key="service_tariff.id", index=True)
    title: str = Field(default="Смета услуг")
    comment: Optional[str] = Field(default=None)

    service_kind: str = Field(default="installation", index=True)
    currency: str = Field(default="BYN")
    subtotal: float = Field(default=0.0)
    discount_amount: float = Field(default=0.0)
    total: float = Field(default=0.0)
    calculation_payload: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    status: str = Field(default="draft", index=True)
    created_by: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)

    customer: Optional["Customer"] = Relationship()
    tariff: Optional["ServiceTariff"] = Relationship()
    items: List["ServiceEstimateItem"] = Relationship(
        back_populates="estimate",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )


class ServiceEstimateItem(SQLModel, table=True):
    __tablename__ = "service_estimate_item"
    id: Optional[int] = Field(default=None, primary_key=True)

    estimate_id: int = Field(foreign_key="service_estimate.id", index=True)
    source_type: str = Field(default="base", index=True)
    source_id: Optional[int] = Field(default=None)
    service_id: Optional[int] = Field(default=None, foreign_key="service.id", index=True)
    name: str

    qty: float = Field(default=1.0)
    unit: str = Field(default="шт")
    unit_price: float = Field(default=0.0)
    line_total: float = Field(default=0.0)
    sort_order: int = Field(default=0)

    estimate: ServiceEstimate = Relationship(back_populates="items")


class OrderProductLink(SQLModel, table=True):
    __tablename__ = "order_product_link"
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    quantity: int = Field(default=1)

    price: int = Field(default=0)
    cost: int = Field(default=0)

    is_installation_included: bool = Field(default=False)
    installation_price: int = Field(default=0)
    installation_details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    order: "Order" = Relationship(back_populates="product_links")
    product: "Product" = Relationship(back_populates="order_links")


class OrderServiceLink(SQLModel, table=True):
    __tablename__ = "order_service_link"
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    service_id: Optional[int] = Field(default=None, foreign_key="service.id")
    quantity: int = Field(default=1)

    title: Optional[str] = Field(default=None)

    price: int = Field(default=0)
    cost: int = Field(default=0)

    order: "Order" = Relationship(back_populates="service_links")
    service: "Service" = Relationship(back_populates="order_links")


class OrderWorkStage(SQLModel, table=True):
    __tablename__ = "order_work_stage"
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)

    name: str  # "Закладка трассы", "Монтаж"
    status: OrderStageStatus = Field(default=OrderStageStatus.PLANNED, sa_column=Column(String, index=True))

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    installer_id: Optional[int] = Field(default=None, foreign_key="installers.id")
    manager_comment: Optional[str] = None
    installer_report: Optional[str] = None

    order: "Order" = Relationship(back_populates="work_stages")
    installer: Optional["Installer"] = Relationship()


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    customer_branch_id: Optional[int] = Field(default=None, foreign_key="customer_branches.id", index=True)
    customer_contract_id: Optional[int] = Field(default=None, foreign_key="customer_contract.id", index=True)

    delivery_address: Optional[str] = None
    document_role_type: Optional[DocumentRoleType] = Field(default=None, sa_column=Column(String, nullable=True))

    user_id: Optional[int] = Field(default=None, index=True)

    status: OrderStatus = Field(default=OrderStatus.NEW_LEAD, sa_column=Column(String, index=True))
    lead_source: LeadSource = Field(default=LeadSource.MANAGER, sa_column=Column(String, index=True))
    title: Optional[str] = Field(default=None)
    comment: Optional[str] = Field(default=None)

    technical_meta: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    total_amount: float = Field(default=0.0)
    total_cost: float = Field(default=0.0)
    margin: float = Field(default=0.0)

    # Financials
    total_payments: float = Field(default=0.0)
    balance_due: float = Field(default=0.0)
    is_paid: bool = Field(default=False) # Will be deprecated but left for now

    # Currency tracking
    target_currency: Optional[PaymentCurrency] = Field(default=None) # 'USD' or 'EUR'
    target_currency_amount: Optional[float] = Field(default=None) # The fixed total price in chosen currency
    target_currency_payments: Optional[float] = Field(default=0.0) # Payments made in chosen currency


    # --- Closing ---
    closing_result: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True, index=True))
    reject_reason: Optional[str] = Field(default=None)

    # --- Pause / On Hold ---
    is_on_hold: bool = Field(default=False, index=True)
    on_hold_reason: Optional[str] = Field(default=None)

    # --- Internal: Negotiation stage ---
    measurement_required: bool = Field(default=False)
    measurement_date: Optional[datetime] = None   # renamed from assessment_date
    measurer_id: Optional[int] = Field(default=None, index=True)
    measurement_result: Optional[str] = Field(default=None)
    proposal_status: str = Field(default="draft", sa_column=Column(String, default="draft", index=True))
    proposal_sent_at: Optional[datetime] = None

    # --- Internal: Execution stage ---
    works_plan: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))

    # Store equipment state
    equipment_status: EquipmentStatus = Field(default=EquipmentStatus.PENDING, sa_column=Column(String, default="pending", index=True))
    standard_install_kit_issued: bool = Field(default=False)


    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})
    installation_date: Optional[datetime] = None
    next_followup_date: Optional[datetime] = Field(default=None, description="Дата следующего касания")
    closed_at: Optional[datetime] = None

    contract_date: Optional[datetime] = Field(default_factory=datetime.now, description="Дата заключения договора")

    customer: Optional["Customer"] = Relationship(back_populates="orders")
    customer_branch: Optional["CustomerBranch"] = Relationship(back_populates="orders")
    customer_contract: Optional["CustomerContract"] = Relationship(back_populates="orders")

    product_links: List[OrderProductLink] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )
    work_stages: List[OrderWorkStage] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )
    service_links: List[OrderServiceLink] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )
    installers: List[OrderInstaller] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )
    documents: List["OrderDocument"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )
    payments: List["Payment"] = Relationship(
        back_populates="order",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
        },
    )

    def calculate_totals(self):
        p_sum = sum([item.price * item.quantity for item in self.product_links])
        s_sum = sum([item.price * item.quantity for item in self.service_links])

        p_cost = sum([item.cost * item.quantity for item in self.product_links])
        s_cost = sum([item.cost * item.quantity for item in self.service_links])

        i_cost = sum([inst.agreed_pay for inst in self.installers])

        self.total_amount = p_sum + s_sum
        self.total_cost = p_cost + s_cost + i_cost
        self.margin = self.total_amount - self.total_cost

        # Infer rate for currency logic if a fixed price is set.
        rate = 1.0
        if self.target_currency and self.target_currency_amount and self.target_currency_amount > 0:
            rate = self.total_amount / self.target_currency_amount

        # Foreign-currency payments only affect totals when the order is fixed in
        # the same target currency.
        byn_amounts = []
        target_amounts = []
        for payment in self.payments:
            curr = getattr(payment, "currency", PaymentCurrency.BYN) or PaymentCurrency.BYN
            if curr == PaymentCurrency.BYN:
                byn_amounts.append(payment.amount)
                if self.target_currency and rate > 0:
                    target_amounts.append(payment.amount / rate)
            elif self.target_currency and curr == self.target_currency:
                target_amounts.append(payment.amount)
                if rate > 0:
                    byn_amounts.append(payment.amount * rate)

        self.total_payments = sum(byn_amounts)
        self.balance_due = max(0.0, self.total_amount - self.total_payments)
        self.target_currency_payments = sum(target_amounts)

    def __str__(self):
        customer_name = self.customer.name if self.customer else "N/A"
        return f"Заказ #{self.id} ({customer_name})"


class OrderDocument(SQLModel, table=True):
    __tablename__ = "order_document"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    doc_type: str = Field(index=True)
    number: str
    date: datetime = Field(default_factory=datetime.now)

    google_file_id: str
    google_edit_url: str

    created_at: datetime = Field(default_factory=datetime.now)

    order: "Order" = Relationship(back_populates="documents")

    def __str__(self):
        return f"{self.doc_type.upper()} {self.number} от {self.date.strftime('%d.%m.%Y')}"


class Payment(SQLModel, table=True):
    __tablename__ = "payment"

    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)

    amount: float = Field(default=0.0)
    currency: PaymentCurrency = Field(default=PaymentCurrency.BYN, sa_column=Column(String, nullable=False, default=PaymentCurrency.BYN.value))
    date: datetime = Field(default_factory=datetime.now)
    type: PaymentType = Field(default=PaymentType.PREPAYMENT, sa_column=Column(String, index=True))

    comment: Optional[str] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, sa_column_kwargs={"onupdate": datetime.now})

    order: "Order" = Relationship(back_populates="payments")

    def __str__(self):
        return f"Платеж {self.amount} BYN от {self.date.strftime('%d.%m.%Y')} ({self.type})"
