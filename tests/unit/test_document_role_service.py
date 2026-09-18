from services.document_role_service import DocumentRoleService
import pytest


def test_executor_customer_role_replacements():
    replacements = DocumentRoleService.build_word_replacements("executor_customer")

    assert replacements["продавцом"] == "исполнителем"
    assert replacements["покупателя"] == "заказчика"
    assert replacements["Продавец"] == "Исполнитель"


def test_contractor_customer_role_replacements():
    replacements = DocumentRoleService.build_word_replacements("contractor_customer")

    assert replacements["продавцом"] == "подрядчиком"
    assert replacements["покупателем"] == "заказчиком"


def test_seller_buyer_role_replacements_are_empty():
    assert DocumentRoleService.build_word_replacements("seller_buyer") == {}
    assert DocumentRoleService.build_word_replacements(None) == {}


@pytest.mark.parametrize('role_type', ['seller_payer', 'executor_payer'])
def test_payer_role_replacements(role_type):
    replacements = DocumentRoleService.build_word_replacements(role_type)
    assert replacements['Покупатель'] == 'Плательщик'
    assert replacements['покупателя'] == 'плательщика'
    assert replacements['покупателю'] == 'плательщику'
    assert replacements['покупателем'] == 'плательщиком'
    assert replacements['покупателе'] == 'плательщике'
