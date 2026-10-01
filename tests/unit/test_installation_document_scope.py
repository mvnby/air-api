from decimal import Decimal
from types import SimpleNamespace

from modules.documents.application.commercial_rows import line_rows
from services.order_service_description import service_line_document_title


def test_grouped_installation_keeps_scope_and_exclusions_in_customer_document():
    link = SimpleNamespace(
        id=41, title="Монтаж настенного кондиционера до 4,2 кВт", service=None,
        price=Decimal("600.00"), quantity=5,
    )
    description = (
        "Трасса 3 м; один проход через стену до 80 см; питание до 5 м; расходные материалы. "
        "Насос и автовышка не включены."
    )

    rows = line_rows([], [(link, 5)], {41: description})

    assert rows[0]["line.title"] == f"{link.title}\n{description}"
    assert rows[0]["line.quantity"] == "5"
    assert rows[0]["line.unit_price"] == "600.00"
    assert rows[0]["line.amount_raw"] == "3000.00"
    assert "Установка №" not in rows[0]["line.title"]


def test_installation_description_does_not_change_legacy_or_other_service_titles():
    legacy = SimpleNamespace(id=1, title="Ранее согласованный состав монтажа", service=None)
    ordinary = SimpleNamespace(id=2, title=None, service=SimpleNamespace(title="Обслуживание"))

    assert service_line_document_title(legacy, {3: "Чужой состав"}) == legacy.title
    assert service_line_document_title(ordinary) == "Обслуживание"


def test_manual_description_is_authoritative_for_customer_document_rows():
    link = SimpleNamespace(id=41, title="Монтаж по договорённости", description="Трасса 5 м",
                           service=None, price=Decimal("550"), quantity=5)
    rows = line_rows([], [(link, 5)], {41: "Трасса 3 м"})
    assert rows[0]["line.title"] == "Монтаж по договорённости\nТрасса 5 м"
    assert Decimal(rows[0]["line.amount_raw"]) == Decimal("2750.00")
    link.description = ""
    assert service_line_document_title(link, {41: "Трасса 3 м"}) == link.title
