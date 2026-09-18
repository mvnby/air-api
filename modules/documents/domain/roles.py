"""Shared Russian party-role vocabulary for legacy and native documents."""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_DOCUMENT_ROLE_TYPE = "seller_buyer"
PARTY_ROLE_DOCUMENT_TYPES = frozenset({"contract", "invoice", "act", "offer"})

@dataclass(frozen=True)
class RoleForms:
    nom: str
    gen: str
    dat: str
    acc: str
    ins: str
    prep: str

    def values(self) -> tuple[str, str, str, str, str, str]:
        return (self.nom, self.gen, self.dat, self.acc, self.ins, self.prep)


SELLER_FORMS = RoleForms("продавец", "продавца", "продавцу", "продавца", "продавцом", "продавце")
BUYER_FORMS = RoleForms("покупатель", "покупателя", "покупателю", "покупателя", "покупателем", "покупателе")
EXECUTOR_FORMS = RoleForms("исполнитель", "исполнителя", "исполнителю", "исполнителя", "исполнителем", "исполнителе")
PAYER_FORMS = RoleForms("плательщик", "плательщика", "плательщику", "плательщика", "плательщиком", "плательщике")

ROLE_FORMS: dict[str, tuple[RoleForms, RoleForms]] = {
    "seller_buyer": (SELLER_FORMS, BUYER_FORMS),
    "executor_customer": (
        EXECUTOR_FORMS,
        RoleForms("заказчик", "заказчика", "заказчику", "заказчика", "заказчиком", "заказчике"),
    ),
    "contractor_customer": (
        RoleForms("подрядчик", "подрядчика", "подрядчику", "подрядчика", "подрядчиком", "подрядчике"),
        RoleForms("заказчик", "заказчика", "заказчику", "заказчика", "заказчиком", "заказчике"),
    ),
    "seller_payer": (SELLER_FORMS, PAYER_FORMS),
    "executor_payer": (EXECUTOR_FORMS, PAYER_FORMS),
}

ROLE_LABELS: dict[str, str] = {
    "seller_buyer": "Продавец / Покупатель",
    "executor_customer": "Исполнитель / Заказчик",
    "contractor_customer": "Подрядчик / Заказчик",
    "seller_payer": "Продавец / Плательщик",
    "executor_payer": "Исполнитель / Плательщик",
}



def role_word_replacements(role_type: str) -> dict[str, str]:
    """Map whole role words from any supported pair; do not touch party data."""
    if role_type not in ROLE_FORMS:
        raise ValueError("Некорректный тип ролей сторон")
    replacements: dict[str, str] = {}
    for source_pair in ROLE_FORMS.values():
        for source, target in zip(source_pair, ROLE_FORMS[role_type]):
            for old, new in zip(source.values(), target.values()):
                for before, after in ((old, new), (old.capitalize(), new.capitalize()), (old.upper(), new.upper())):
                    replacements[before] = after
    return replacements
