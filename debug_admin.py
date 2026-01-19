from admin.orders import OrderAdmin
from models import OrderStatus

print("OrderAdmin form_args:", OrderAdmin.form_args)
print("OrderAdmin form_overrides:", OrderAdmin.form_overrides)

# Check choices generation
STATUS_LABELS = {
    "new_lead": "Новый лид",
    "assessment": "Замер/Осмотр",
    "proposal": "КП отправлено",
    "negotiation": "Переговоры",
    "won_deposit": "Сделка (Предоплата)",
    "installation": "Монтаж",
    "completed": "Закрыто (Успех)",
    "canceled": "Отмена",
    "deferred": "Отложено"
}
expected_choices = [(s.value, STATUS_LABELS.get(s.value, s.value)) for s in OrderStatus]
print("\nExpected Choices:")
for v, l in expected_choices:
    print(f"  {v}: {l}")
