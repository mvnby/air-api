from sqladmin import ModelView
from models import Customer, CustomerType

from .common_constants import PAGE_SIZE_SMALL


class CustomerAdmin(ModelView, model=Customer):
    name = "Клиент"
    name_plural = "Клиенты"
    icon = "fa-solid fa-user-tie"
    extra_js = ["/static/js/admin_customers.js"]
    
    # List view
    column_list = [
        Customer.id, Customer.name, 
        Customer.inn, Customer.email, Customer.phone
    ]
    column_searchable_list = [Customer.name, Customer.phone, Customer.inn, Customer.email]
    column_default_sort = (Customer.created_at, True)
    page_size = PAGE_SIZE_SMALL
    
    # Labels
    column_labels = {
        "id": "ID",
        "name": "Название",
        "phone": "Телефон",
        "email": "Email",
        "type": "Тип",
        "full_legal_name": "Полное наименование",
        "inn": "УНП",
        "kpp": "ОКПО",
        "legal_address": "Юр. адрес",
        "actual_address": "Почтовый адрес",
        "bank_name": "Банк",
        "bic": "БИК",
        "iban": "Расчетный счет",
        "signer_position": "Должность подписанта",
        "signer_name": "ФИО подписанта",
        "acting_basis": "Действует на основании",
        "created_at": "Создан",
    }
    
    # Form field grouping
    form_columns = [
        # Contact Info
        "name", "phone", "email", "type",
        # Legal Details
        "full_legal_name", "inn", "kpp", "legal_address", "actual_address",
        # Bank Details
        "bank_name", "bic", "iban",
        # Signatory
        "signer_position", "signer_name", "acting_basis",
    ]
    
    # Form rules for visual grouping (if supported)
    form_edit_rules = form_columns
    form_create_rules = form_columns
    
    # Type choices
    form_choices = {
        "type": [
            (CustomerType.individual.value, "Физлицо"),
            (CustomerType.company.value, "Юрлицо"),
        ]
    }

    def __str__(self):
        return self.name
