from enum import Enum


class CustomerType(str, Enum):
    individual = "individual"
    company = "company"


class LeadStatus(str, Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    lost = "lost"
    spam = "spam"


class LeadIntakeSource(str, Enum):
    phone = "phone"
    site = "site"
    bot = "bot"
    email = "email"
    manager = "manager"
    other = "other"


class LeadSegmentHint(str, Enum):
    unknown = "unknown"
    b2c = "b2c"
    b2b = "b2b"


class LeadLossReason(str, Enum):
    no_product = "no_product"
    no_budget = "no_budget"
    no_response = "no_response"
    duplicate = "duplicate"
    spam = "spam"
    other = "other"


class OrderStatus(str, Enum):
    NEW_LEAD    = "new_lead"      # Входящий лид (Inbox)
    NEGOTIATION = "negotiation"   # Переговоры
    EXECUTION   = "execution"     # Монтаж
    CLOSED      = "closed"        # Архив (завершено)


class ClosingResult(str, Enum):
    WON  = "won"   # Успех
    LOST = "lost"  # Отказ


class LeadSource(str, Enum):
    """Источник лида - откуда пришёл клиент"""

    SITE = "site"
    BOT = "bot"
    PHONE = "phone"
    EMAIL = "email"
    MANAGER = "manager"
    REFERRAL = "referral"
    OTHER = "other"


class PaymentType(str, Enum):
    PREPAYMENT = "prepayment"
    POSTPAYMENT = "postpayment"


class PaymentCurrency(str, Enum):
    BYN = "BYN"
    USD = "USD"
    EUR = "EUR"


class SupplierPaymentMethod(str, Enum):
    CASH = "cash"
    BANK = "bank"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class SupplierContactChannel(str, Enum):
    PHONE = "phone"
    VIBER = "viber"
    TELEGRAM = "telegram"
    EMAIL = "email"
    OTHER = "other"


class SupplyRequestIntent(str, Enum):
    RESERVE = "reserve"
    ORDER = "order"


class SupplyRequestStatus(str, Enum):
    DRAFT = "draft"
    AWAITING_REPLY = "awaiting_reply"
    RESERVED = "reserved"
    ORDERED = "ordered"
    READY_FOR_PICKUP = "ready_for_pickup"
    PICKED_UP = "picked_up"
    RECEIVED = "received"
    CANCELED = "canceled"


class SupplyRequestLineSourceType(str, Enum):
    ORDER_LINE = "order_line"
    STOCK = "stock"
    MANUAL = "manual"


class DocumentRoleType(str, Enum):
    SELLER_BUYER = "seller_buyer"
    EXECUTOR_CUSTOMER = "executor_customer"
    CONTRACTOR_CUSTOMER = "contractor_customer"


class OrderStageStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELED = "canceled"


class EquipmentStatus(str, Enum):
    PENDING = "pending"
    RESERVED = "reserved"
    ISSUED = "issued"


class EquipmentServiceEventType(str, Enum):
    DIAGNOSTIC = "diagnostic"
    REPAIR = "repair"
    MAINTENANCE = "maintenance"
    REFRIGERANT_CHARGE = "refrigerant_charge"
    LEAK = "leak"
    RECOMMENDATION = "recommendation"
    NOT_REPAIRABLE = "not_repairable"
    OTHER = "other"
