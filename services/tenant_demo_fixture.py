"""Static, non-routable records used by the reviewed tenant demo seed."""

from dataclasses import dataclass

from models.common import CustomerType, OrderStatus


FIXTURE_VERSION = "v1"


@dataclass(frozen=True)
class DemoCustomerSpec:
    name: str
    phone: str
    email: str
    customer_type: CustomerType
    city: str
    address: str


@dataclass(frozen=True)
class DemoOrderSpec:
    customer_index: int
    offer_index: int
    title: str
    status: OrderStatus
    delivery_address: str
    comment: str


DEMO_CUSTOMERS = (
    DemoCustomerSpec(
        name="[ДЕМО] Анна Климатова",
        phone="Не указан (демо 1)",
        email="anna.demo@example.invalid",
        customer_type=CustomerType.individual,
        city="Минск (пример)",
        address="[ДЕМО] г. Минск, ул. Примерная, 1",
    ),
    DemoCustomerSpec(
        name="[ДЕМО] Семья Новиковых",
        phone="Не указан (демо 2)",
        email="novikovy.demo@example.invalid",
        customer_type=CustomerType.individual,
        city="Минск (пример)",
        address="[ДЕМО] г. Минск, пр-т Учебный, 12",
    ),
    DemoCustomerSpec(
        name="[ДЕМО] Компания «Пример»",
        phone="Не указан (демо 3)",
        email="company.demo@example.invalid",
        customer_type=CustomerType.company,
        city="Минск (пример)",
        address="[ДЕМО] г. Минск, пер. Демонстрационный, 3",
    ),
)


DEMO_ORDERS = (
    DemoOrderSpec(
        customer_index=0,
        offer_index=0,
        title="[ДЕМО] Кондиционер для квартиры",
        status=OrderStatus.NEGOTIATION,
        delivery_address="[ДЕМО] г. Минск, ул. Примерная, 1",
        comment="Учебный заказ: подбор и согласование модели.",
    ),
    DemoOrderSpec(
        customer_index=2,
        offer_index=1,
        title="[ДЕМО] Климат для небольшого офиса",
        status=OrderStatus.EXECUTION,
        delivery_address="[ДЕМО] г. Минск, пер. Демонстрационный, 3",
        comment="Учебный заказ: оборудование согласовано, монтаж планируется.",
    ),
)


__all__ = ["DEMO_CUSTOMERS", "DEMO_ORDERS", "FIXTURE_VERSION"]
