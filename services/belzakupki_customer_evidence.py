"""Extract customer and submission evidence from a Belzakupki detail response.

The extractor is deliberately read-only. Each document is inspected on its own,
and requisites are associated with the nearest identified legal party.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.input_validation import (
    validate_optional_bic,
    validate_optional_iban,
    validate_optional_unp,
)
from schemas_belzakupki_enrichment import SourceContactDraft, SourceCustomerDraft, SourceSubmissionDraft
from services.customer_party_classifier import infer_customer_type_from_requisites


_UNP = re.compile(
    r"(?<!\w)УНП\s*[:№-]?\s*"
    r"([0-9ЗзОоOoІіIiLl]{1,15}(?:[ \t-]+[0-9ЗзОоOoІіIiLl]{2,9})*)"
    r"(?![\w/])", re.I,
)
_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE = re.compile(r"(?:\+375|8\s*0)\s*\(?\d{2}\)?[\s()-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
_IBAN = re.compile(r"(?<!\w)BY\s*\d{2}(?:[\s|]*[A-ZА-ЯІ0-9]){24}(?!\w)", re.I)
_BIC = re.compile(r"(?:Б[ИIІ]К|BIC|SWIFT)\s*[:№-]?\s*([A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)(?!\w)", re.I)
_PLATFORM = re.compile(
    r"(?:предложени\w*|заявк\w*)[^.!?]{0,250}?"
    r"(?:предостав\w*|пода(?:ю|е|ё|ва|ть)\w*|направ(?:ля|ить)\w*|размеща\w*)[^.!?]{0,250}?"
    r"(?:на\s+ЭТП|через\s+ЭТП|на\s+электронн\w* торгов\w* площадк\w*)", re.I,
)
_SUBMISSION_EMAIL = re.compile(
    r"(?:сведени\w*|предложени\w*|заявк\w*).{0,250}?"
    r"(?:представля\w*|направля\w*|пода\w*|отправля\w*).{0,160}?"
    r"(?:электронн\w* почт\w*|e-?mail).{0,100}?"
    + _EMAIL.pattern, re.I,
)
_BRANCH = re.compile(r"\b(?:филиал|філіял)\b\s*[«\"\s]*([^\n.;|]{3,180})", re.I)
_BANK_NAME = re.compile(r"\b(?:ОАО|ЗАО|АБ)\b\s*[«\"]?[^\n;|]{0,100}?банк[»\"]?", re.I)


@dataclass
class CustomerEvidence:
    customer: SourceCustomerDraft
    related_customers: list[SourceCustomerDraft] = field(default_factory=list)
    contacts: list[SourceContactDraft] = field(default_factory=list)
    submission: SourceSubmissionDraft = field(default_factory=lambda: SourceSubmissionDraft(method="unknown"))
    field_sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _PartyBlock:
    unp: str
    raw_unp: str
    name: str | None
    text: str
    source: str
    branch: bool


def _clean(value: Any, limit: int = 500) -> str | None:
    text = " ".join(str(value or "").split())
    return text[:limit] or None


def _valid_unp(value: Any) -> str | None:
    try:
        return validate_optional_unp(str(value)) if value is not None else None
    except ValueError:
        return None


def _source_label(document: dict[str, Any]) -> str:
    return _clean(document.get("name"), 255) or f"Документ {document.get('id', '')}".strip()


def _matches_party_name(name: str | None, text: str) -> bool:
    if not name:
        return False
    words = re.findall(r"[а-яёa-z]{4,}", name.casefold())
    generic = {"учреждение", "здравоохранения", "республиканское", "унитарное", "предприятие",
               "автомобильных", "дорог", "общество", "ограниченной", "ответственностью"}
    words = [word for word in words if word not in generic]
    present = set(re.findall(r"[а-яёa-z]{4,}", text.casefold()))
    return bool(words) and all(word in present for word in words)


def _party_name(before: str, *, parent_name: str | None, parent_unp: str | None, unp: str) -> tuple[str | None, bool]:
    # Branches are separate legal blocks even when the parent name is repeated.
    branch = list(_BRANCH.finditer(before[-500:]))
    if branch and _matches_party_name(parent_name, before[-800:]):
        candidate = _clean("филиал " + branch[-1].group(1), 500)
        return candidate, True
    if unp == parent_unp and parent_name:
        return parent_name, False
    if _matches_party_name(parent_name, before):
        return parent_name, False
    if parent_name:
        parent_position = before.casefold().rfind(parent_name.casefold())
        if parent_position >= 0 and not re.search(
            r"\b(?:поставщик|исполнитель|филиал)\b", before[parent_position + len(parent_name):], re.I,
        ):
            return parent_name, False
    tail = before[-600:]
    role = list(re.finditer(r"(?:заказчик|организатор|покупатель)\s*[:\-–]?\s*", tail, re.I))
    if role:
        candidate = _clean(tail[role[-1].end():], 500)
        return candidate, False
    return None, False


def _party_blocks(document: dict[str, Any], parent_name: str | None, parent_unp: str | None) -> list[_PartyBlock]:
    raw = str(document.get("extracted_text") or "")
    # Table extraction uses pipes as cell boundaries. Keep line boundaries for
    # bank-name evidence, but let numeric identifiers span adjacent cells.
    text = re.sub(r"[ \t]*\|[ \t]*", " ", raw)
    matches: list[tuple[re.Match[str], str, str | None, bool]] = []
    previous_end = 0
    for match in _UNP.finditer(text):
        unp = _valid_unp(match.group(1))
        if not unp:
            continue
        name, branch = _party_name(text[max(previous_end, match.start() - 3000):match.start()],
                                   parent_name=parent_name, parent_unp=parent_unp, unp=unp)
        matches.append((match, unp, name, branch))
        previous_end = match.end()
    blocks: list[_PartyBlock] = []
    for index, (match, unp, name, branch) in enumerate(matches):
        end = matches[index + 1][0].start() if index + 1 < len(matches) else len(text)
        # Do not borrow bank details from a later party or an unrelated appendix.
        start = matches[index - 1][0].end() if index else 0
        start = max(start, match.start() - 3000)
        before = text[start:match.start()]
        headings = list(re.finditer(r"(?:^|\n)\s*(?:ПОСТАВЩИК|ПОКУПАТЕЛЬ|ЗАКАЗЧИК|ОРГАНИЗАТОР)\b", before, re.I))
        if headings:
            start += headings[-1].start()
        body = text[start:min(end, match.end() + 3000)]
        after = text[match.end():min(end, match.end() + 3000)]
        next_party = re.search(r"(?:^|\n)\s*(?:ПОСТАВЩИК|ПОКУПАТЕЛЬ|ЗАКАЗЧИК|ОРГАНИЗАТОР)\b", after, re.I)
        if next_party:
            body = text[start:match.end() + next_party.start()]
        if not branch:
            next_branch = _BRANCH.search(body)
            if next_branch:
                body = body[:next_branch.start()]
        blocks.append(_PartyBlock(unp, match.group(1).strip(), name, body, _source_label(document), branch))
    return blocks


def _bank_fields(block: _PartyBlock) -> dict[str, str]:
    result: dict[str, str] = {}
    iban_matches = list(_IBAN.finditer(block.text))
    ibans = set()
    for iban_match in iban_matches:
        try:
            ibans.add(validate_optional_iban(iban_match.group(0)))
        except ValueError:
            pass
    if len(ibans) == 1:
        result["iban"] = ibans.pop() or ""
    bic_match = _BIC.search(block.text)
    if bic_match:
        try:
            result["bic"] = validate_optional_bic(bic_match.group(1)) or ""
        except ValueError:
            pass
    bank_match = _BANK_NAME.search(block.text)
    if bank_match:
        result["bank_name"] = _clean(bank_match.group(0), 255) or ""
    return result


def _email_evidence(text: str, match: re.Match[str]) -> str:
    start = max(text.rfind("\n", 0, match.start()) + 1, match.start() - 100)
    end_line = text.find("\n", match.end())
    end = min(end_line if end_line >= 0 else len(text), match.end() + 140)
    return _clean(text[start:end], 300) or match.group(0)


def _submission_candidates(document: dict[str, Any], source_url: str | None) -> list[SourceSubmissionDraft]:
    raw = str(document.get("extracted_text") or "")
    # A sentence-sized window avoids inferring submission from contractual email
    # clauses elsewhere in the document.
    collapsed = " ".join(re.sub(r"\s*\|\s*", " ", raw).split())
    result: list[SourceSubmissionDraft] = []
    for match in _SUBMISSION_EMAIL.finditer(collapsed):
        emails = list(_EMAIL.finditer(match.group(0)))
        if emails:
            result.append(SourceSubmissionDraft(
                method="email", email=emails[-1].group(0).lower(),
                evidence=_clean(match.group(0), 500), source=_source_label(document),
            ))
    for match in _PLATFORM.finditer(collapsed):
        result.append(SourceSubmissionDraft(
            method="platform", url=source_url,
            evidence=_clean(match.group(0), 500), source=_source_label(document),
        ))
    return result


def extract_customer_evidence(data: dict[str, Any]) -> CustomerEvidence:
    """Return source-backed drafts without persisting or guessing missing facts."""
    source_customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    contacts_data = source_customer.get("contacts") if isinstance(source_customer.get("contacts"), dict) else {}
    name = _clean(source_customer.get("name") or data.get("customer_name"), 500)
    unp = _valid_unp(source_customer.get("unp"))
    source_emails = list(dict.fromkeys(email.lower() for email in _EMAIL.findall(
        str(contacts_data.get("email") or ""))))
    source_phone_match = _PHONE.search(str(contacts_data.get("phone") or contacts_data.get("name") or ""))
    customer = SourceCustomerDraft(
        name=name, inn=unp, type="company", email=source_emails[0] if len(source_emails) == 1 else None,
        phone=source_phone_match.group(0) if source_phone_match else None,
        legal_address=_clean(source_customer.get("legal_address"), 500),
    )
    result = CustomerEvidence(customer=customer)
    customer.type = infer_customer_type_from_requisites({"name": name, "inn": unp}).value
    if customer.type == "individual" and name:
        customer.type = "company"
    result.field_sources["customer.type"] = "Определено по реквизитам заказчика"
    if name:
        result.field_sources["customer.name"] = "Карточка закупки"
    if unp:
        result.field_sources["customer.inn"] = "Карточка закупки"
        if _clean(source_customer.get("unp")) != unp:
            result.warnings.append("УНП восстановлен из похожих символов в карточке закупки; проверьте оригинал.")
    elif source_customer.get("unp"):
        result.warnings.append("УНП в карточке закупки не распознан; проверьте оригинал.")
    for key in ("phone", "email", "legal_address"):
        if getattr(customer, key):
            result.field_sources[f"customer.{key}"] = "Карточка закупки"

    seen_contacts: set[tuple[str, str]] = set()

    def add_contact(email: str, purpose: str, source: str, evidence: str) -> None:
        key = (email.lower(), purpose)
        if key not in seen_contacts:
            seen_contacts.add(key)
            result.contacts.append(SourceContactDraft(
                email=email.lower(), purpose=purpose, source=source, evidence=evidence,
            ))

    for email in source_emails:
        add_contact(email, "general", "Карточка закупки", str(contacts_data.get("email") or email)[:1000])

    related_by_unp: dict[str, SourceCustomerDraft] = {}
    candidates: list[SourceSubmissionDraft] = []
    documents = data.get("documents") if isinstance(data.get("documents"), list) else []
    for document in documents:
        if not isinstance(document, dict):
            continue
        source = _source_label(document)
        blocks = _party_blocks(document, name, unp)
        for block in blocks:
            if _clean(block.raw_unp) != block.unp:
                result.warnings.append(f"УНП восстановлен из похожих символов в документе «{source}»; проверьте оригинал: {block.raw_unp}.")
            if block.unp == unp:
                target = customer
                prefix = "customer"
            elif block.branch and block.name:
                target = related_by_unp.get(block.unp)
                if target is None:
                    target = SourceCustomerDraft(name=block.name, inn=block.unp, type="company")
                    related_by_unp[block.unp] = target
                prefix = f"related_customers.{list(related_by_unp).index(block.unp)}"
                result.field_sources[f"{prefix}.inn"] = source
                result.field_sources[f"{prefix}.name"] = source
            elif unp is None and block.name and _matches_party_name(name, block.name):
                target = customer
                prefix = "customer"
                customer.inn = block.unp
                unp = block.unp
                result.field_sources["customer.inn"] = source
            else:
                continue
            for key, value in _bank_fields(block).items():
                if not getattr(target, key, None):
                    setattr(target, key, value)
                    result.field_sources[f"{prefix}.{key}"] = source
            for match in _EMAIL.finditer(block.text):
                email = match.group(0).lower()
                add_contact(email, "general", source, _email_evidence(block.text, match))
                if target is not customer and not target.email:
                    target.email = email
                    result.field_sources[f"{prefix}.email"] = source
        candidates.extend(_submission_candidates(document, _clean(data.get("source_url"), 2048)))
        if document.get("extracted_text_truncated"):
            result.warnings.append(f"Текст документа «{source}» обрезан; проверьте реквизиты по оригиналу.")

    result.related_customers = list(related_by_unp.values())
    choices = {(item.method, item.email) for item in candidates}
    if len(choices) == 1:
        result.submission = candidates[0]
        if result.submission.email:
            add_contact(result.submission.email, "submission", result.submission.source or "Документ",
                        result.submission.evidence or result.submission.email)
            customer.email = result.submission.email
            result.field_sources["customer.email"] = result.submission.source or "Документ"
    elif len(choices) > 1:
        result.submission = SourceSubmissionDraft(method="unknown", evidence="; ".join(
            item.evidence or "" for item in candidates[:3]), source="Несколько документов")
        result.warnings.append("Способ подачи противоречив в документах; проверьте оригиналы.")
    return result
