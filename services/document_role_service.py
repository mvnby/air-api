from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from models import DocumentRoleType
from modules.documents.domain.roles import (
    BUYER_FORMS,
    SELLER_FORMS,
    ROLE_FORMS,
    ROLE_LABELS,
)


DEFAULT_DOCUMENT_ROLE_TYPE = DocumentRoleType.SELLER_BUYER.value


class DocumentRoleService:
    @staticmethod
    def normalize_role_type(raw: Optional[Any]) -> str:
        value = raw.value if hasattr(raw, "value") else raw
        value = str(value or "").strip()
        return value if value in ROLE_FORMS else DEFAULT_DOCUMENT_ROLE_TYPE

    @staticmethod
    def nullable_role_type(raw: Optional[Any]) -> Optional[str]:
        if raw is None:
            return None
        value = raw.value if hasattr(raw, "value") else raw
        value = str(value or "").strip()
        if not value:
            return None
        if value not in ROLE_FORMS:
            raise ValueError("Некорректный тип ролей сторон")
        return value

    @staticmethod
    def effective_role_type(order: Any) -> str:
        order_role = DocumentRoleService.normalize_role_type(getattr(order, "document_role_type", None))
        if getattr(order, "document_role_type", None):
            return order_role
        contract = getattr(order, "customer_contract", None)
        return DocumentRoleService.normalize_role_type(getattr(contract, "document_role_type", None))

    @staticmethod
    def role_options() -> list[dict[str, str]]:
        return [{"value": value, "label": label} for value, label in ROLE_LABELS.items()]

    @staticmethod
    def role_label(raw: Optional[Any]) -> str:
        return ROLE_LABELS[DocumentRoleService.normalize_role_type(raw)]

    @staticmethod
    def _with_capitalized_forms(words: Iterable[str]) -> list[str]:
        result: list[str] = []
        for word in words:
            result.append(word)
            result.append(word[:1].upper() + word[1:])
        return result

    @staticmethod
    def build_word_replacements(raw_role_type: Optional[Any]) -> Dict[str, str]:
        role_type = DocumentRoleService.normalize_role_type(raw_role_type)
        if role_type == DEFAULT_DOCUMENT_ROLE_TYPE:
            return {}

        seller_target, buyer_target = ROLE_FORMS[role_type]
        replacements: Dict[str, str] = {}
        for source, target in zip(
            DocumentRoleService._with_capitalized_forms(SELLER_FORMS.values()),
            DocumentRoleService._with_capitalized_forms(seller_target.values()),
        ):
            replacements[source] = target
        for source, target in zip(
            DocumentRoleService._with_capitalized_forms(BUYER_FORMS.values()),
            DocumentRoleService._with_capitalized_forms(buyer_target.values()),
        ):
            replacements[source] = target
        return replacements
