from services.belzakupki_customer_evidence import extract_customer_evidence
import json
from pathlib import Path


def _detail(customer, text, *, number, source_url="https://zakupki.example/tender"):
    return {
        "customer": customer, "source_url": source_url,
        "documents": [{"id": number, "name": f"Документ {number}", "extracted_text": text}],
    }


def test_464_parent_requisites_and_submission_email_have_distinct_evidence():
    data = _detail(
        {"name": "Витебская областная клиническая больница", "unp": "300050210",
         "contacts": {"email": "info@vokb.by"}},
        "| Заказчик | Витебская областная клиническая больница |\n"
        "| Юридический адрес | г. Витебск |\n"
        "| УНП | 300050210 |\n"
        "| Р/с | BY35BLBB36040300050210001001 |\n"
        "| БИК | BLBBBY2X |\n"
        "| Банк | ОАО «Белинвестбанк» |\n"
        "Сведения представляются на электронную почту: (marketing@vokb.vitebsk.by).",
        number=464,
    )
    evidence = extract_customer_evidence(data)
    assert evidence.customer.name == "Витебская областная клиническая больница"
    assert evidence.customer.inn == "300050210"
    assert evidence.customer.iban == "BY35BLBB36040300050210001001"
    assert evidence.customer.bic == "BLBBBY2X"
    assert evidence.customer.bank_name == "ОАО «Белинвестбанк»"
    assert evidence.customer.email == "marketing@vokb.vitebsk.by"
    assert evidence.submission.method == "email"
    assert evidence.submission.email == "marketing@vokb.vitebsk.by"
    assert {(c.email, c.purpose) for c in evidence.contacts} == {
        ("info@vokb.by", "general"), ("marketing@vokb.vitebsk.by", "general"),
        ("marketing@vokb.vitebsk.by", "submission"),
    }


def test_466_branch_is_separate_party_and_platform_submission():
    data = _detail(
        {"name": "Республиканское унитарное предприятие Витебскавтодор", "unp": "300582165"},
        "Заказчик: Республиканское унитарное предприятие Витебскавтодор, УНП 300582165.\n"
        "филиал ДЭУ №32 РУП Витебскавтодор, УНП З002З0565\n"
        "р/с BY43 BLBB 3012 0300 2305 6500 1001, БИК BLBBBY2X, ОАО «Белинвестбанк»\n"
        "Электронная почта: ppo@deu32.vitebsk.by, priem@deu32.vitebsk.by\n"
        "Поставщик: 9-я поликлиника, УНП 100126696\n"
        "Предложение предоставляется участником посредством его размещения на ЭТП "
        "с обязательным подписанием электронной цифровой подписью.",
        number=466,
    )
    evidence = extract_customer_evidence(data)
    assert evidence.customer.inn == "300582165"
    assert evidence.customer.iban is None
    assert len(evidence.related_customers) == 1
    branch = evidence.related_customers[0]
    assert branch.inn == "300230565"
    assert branch.iban == "BY43BLBB30120300230565001001"
    assert {c.email for c in evidence.contacts} == {
        "ppo@deu32.vitebsk.by", "priem@deu32.vitebsk.by",
    }
    assert evidence.submission.method == "platform"
    assert evidence.submission.url == data["source_url"]
    assert any("З002З0565" in warning for warning in evidence.warnings)


def test_contract_email_is_not_submission_and_conflicts_need_review():
    data = _detail(
        {"name": "ОАО Заказчик", "unp": "123456789"},
        "Заказчик ОАО Заказчик, УНП 123456789. Договор отправляется по электронной почте "
        "info@example.by.", number=1,
    )
    assert extract_customer_evidence(data).submission.method == "unknown"
    data["documents"].extend([
        {"id": 2, "name": "Email", "extracted_text": "Сведения представляются на электронную почту: bid@example.by"},
        {"id": 3, "name": "ЭТП", "extracted_text": "Предложение предоставляется посредством его размещения на ЭТП."},
    ])
    evidence = extract_customer_evidence(data)
    assert evidence.submission.method == "unknown"
    assert evidence.warnings


def test_invalid_overlong_source_unp_is_not_truncated_into_identity():
    evidence = extract_customer_evidence({"customer": {"name": "ОАО Заказчик", "unp": "1234567890"}})
    assert evidence.customer.inn is None
    assert any("не распознан" in warning for warning in evidence.warnings)


def test_document_unp_with_extra_character_is_not_reduced_to_valid_prefix():
    for token in ("300230565X", "300230565/9", "3002305650"):
        evidence = extract_customer_evidence(_detail(
            {"name": "ОАО Заказчик"}, f"Заказчик ОАО Заказчик, УНП {token}", number=1,
        ))
        assert evidence.customer.inn is None


def test_deadlines_and_clarification_answers_are_not_submission_channel():
    for text in (
        "Срок для подготовки и подачи предложений: с даты размещения на ЭТП.",
        "До истечения срока для подготовки и подачи предложений. Ответ размещается на ЭТП.",
    ):
        assert extract_customer_evidence(_detail({}, text, number=1)).submission.method == "unknown"


def test_live_464_bilingual_word_table_keeps_bank_before_unp_and_submission_email():
    data = json.loads((Path(__file__).parents[1] / "fixtures/tender_customer/464.json").read_text())
    evidence = extract_customer_evidence(data)
    assert evidence.customer.inn == "300050210"
    assert evidence.customer.iban == "BY35BLBB36040300050210001001"
    assert evidence.customer.bic == "BLBBBY2X"
    assert evidence.customer.bank_name == "ОАО «Белинвестбанк»"
    assert evidence.customer.email == "marketing@vokb.vitebsk.by"
    assert {contact.email for contact in evidence.contacts} == {"info@vokb.by", "marketing@vokb.vitebsk.by"}
    assert evidence.submission.method == "email"


def test_live_466_ocr_and_contract_keep_only_related_branch_and_explicit_platform():
    data = json.loads((Path(__file__).parents[1] / "fixtures/tender_customer/466.json").read_text())
    evidence = extract_customer_evidence(data)
    assert evidence.customer.inn == "300582165"
    assert evidence.customer.iban is None
    assert [item.inn for item in evidence.related_customers] == ["300230565"]
    assert evidence.related_customers[0].iban == "BY43BLBB30120300230565001001"
    assert {contact.email for contact in evidence.contacts} == {"ppo@deu32.vitebsk.by", "priem@deu32.vitebsk.by"}
    assert evidence.submission.method == "platform"
    assert "Предложение предостав" in evidence.submission.evidence
