from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from models import Customer
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import ManagerOrderSourceApply, SourceCustomerDraft
from services.belzakupki_customer_service import apply_reviewed_customer, enrich_registry


@pytest.mark.asyncio
async def test_review_fills_missing_requisites_without_overwriting_staff_values(monkeypatch):
    customer = Customer(id=501, tenant_id=1, name="Больница", phone="+375291112233", email="staff@example.by")
    draft = SourceCustomerDraft(name="Больница", inn="300050210", phone="+375212616343",
                                email="marketing@vokb.vitebsk.by", legal_address="г. Витебск",
                                iban="BY35BLBB36040300050210001001", bic="BLBBBY2X")
    monkeypatch.setattr("services.belzakupki_customer_service.TenantEntityAccessService.get_customer", AsyncMock(return_value=customer))
    applied = []
    result = await apply_reviewed_customer(AsyncMock(), order=SimpleNamespace(), scope=TenantScope(1, 1),
        payload=ManagerOrderSourceApply(customer_action="existing", customer_id=501, customer=draft),
        evidence=SimpleNamespace(customer=draft, related_customers=[]), applied=applied)
    assert result is customer
    assert customer.inn == "300050210" and customer.iban == draft.iban
    assert customer.phone == "+375291112233" and customer.email == "staff@example.by"
    assert applied == ["customer_requisites"]


@pytest.mark.asyncio
async def test_review_accepts_documented_branch_but_rejects_foreign_party(monkeypatch):
    main = SourceCustomerDraft(name="Витебскавтодор", inn="300582165")
    branch = SourceCustomerDraft(name="Филиал ДЭУ №32", inn="300230565")
    customer = Customer(id=5, tenant_id=1, name=branch.name, phone="", inn=branch.inn)
    lookup = AsyncMock(return_value=customer)
    monkeypatch.setattr("services.belzakupki_customer_service.TenantEntityAccessService.get_customer", lookup)
    evidence = SimpleNamespace(customer=main, related_customers=[branch])
    await apply_reviewed_customer(AsyncMock(), order=SimpleNamespace(), scope=TenantScope(1, 1),
        payload=ManagerOrderSourceApply(customer_action="existing", customer_id=5, customer=branch),
        evidence=evidence, applied=[])
    foreign = SourceCustomerDraft(name="Поликлиника", inn="100126696")
    with pytest.raises(ValueError, match="UNP does not match"):
        await apply_reviewed_customer(AsyncMock(), order=SimpleNamespace(), scope=TenantScope(1, 1),
            payload=ManagerOrderSourceApply(customer_action="existing", customer_id=5, customer=foreign),
            evidence=evidence, applied=[])
    assert lookup.await_count == 1


@pytest.mark.asyncio
async def test_registry_verifies_unp_before_using_returned_identity(monkeypatch):
    draft = SourceCustomerDraft(name="Черновик", inn="300582165")
    evidence = SimpleNamespace(customer=draft, related_customers=[], field_sources={}, warnings=[])
    fetch = AsyncMock(return_value={"row": {"vunp": "300582165", "vnaimp": "РУП Витебскавтодор", "vpadres": "ул. Суворова, 16"}})
    monkeypatch.setattr("services.belzakupki_customer_service.fetch_registry_data", fetch)
    await enrich_registry(evidence)
    assert draft.name == "РУП Витебскавтодор" and draft.legal_address == "ул. Суворова, 16"
    assert draft.type == "company"
    fetch.return_value = {"row": {"vunp": "100126696", "vnaimp": "Чужое учреждение"}}
    await enrich_registry(evidence)
    assert draft.name == "РУП Витебскавтодор"
    assert evidence.warnings
