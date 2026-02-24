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
