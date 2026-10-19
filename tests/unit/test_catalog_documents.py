from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import selectinload
from sqlmodel import SQLModel

from models import Brand, Product, ProductSeries
from models.catalog_document import CatalogDocument
from schemas_catalog_documents import CatalogDocumentInput, CatalogDocumentsReplacePayload
from services.catalog_document_service import CatalogDocumentService
from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService


@pytest_asyncio.fixture
async def document_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: SQLModel.metadata.create_all(sync, tables=[
            Brand.__table__, ProductSeries.__table__, Product.__table__, CatalogDocument.__table__,
        ]))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add_all([
            Brand(id=1, title="Example", slug="example"),
            Brand(id=2, title="Other", slug="other"),
            ProductSeries(id=3, brand_id=1, title="Premium", slug="premium"),
            Product(id=4, brand_id=1, series_id=3, title="Unit", slug="unit", price=1000),
            Product(id=5, brand_id=1, series_id=3, title="Unit 2", slug="unit-2", price=1200),
        ])
        await session.commit()
        yield session
    await engine.dispose()


def _document(*, title="Material", url="https://example.com/manual.pdf", **fields):
    return CatalogDocument(title=title, url=url, kind="operation", **fields)


@pytest.mark.asyncio
async def test_inherits_all_distinct_documents_with_specific_origin_and_override(document_session):
    document_session.add_all([
        _document(brand_id=1, title="Brand", url="https://example.com/catalog.pdf"),
        _document(series_id=3, title="Series", url="https://example.com/manual.pdf"),
        _document(brand_id=1, title="Old title", url="https://example.com/manual.pdf"),
        _document(product_id=4, title="Model", url="https://example.com/catalog.pdf"),
        _document(series_id=3, title="Second manual", url="https://example.com/manual-2.pdf"),
    ])
    await document_session.commit()
    result = await CatalogDocumentService.get_workspace(document_session, target_type="product", target_id=4)
    assert len(result.own) == 1
    assert len(result.inherited) == 4
    assert [(item.title, item.origin_type) for item in result.effective] == [
        ("Model", "product"), ("Series", "series"), ("Second manual", "series"),
    ]
    assert result.effective[1].origin_title == "Premium"
    assert result.effective[1].inherited is True


@pytest.mark.asyncio
async def test_internal_documents_and_provenance_are_not_public(document_session):
    document_session.add_all([
        _document(brand_id=1, visibility="internal", url="https://example.com/research.pdf"),
        _document(series_id=3, source_url="https://example.com/supplier-notes"),
        # A private model override suppresses the same public series reference.
        _document(product_id=4, visibility="internal"),
        _document(series_id=3, url="https://example.com/public.pdf", source_url="https://example.com/provenance"),
    ])
    await document_session.commit()
    manager = await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4, public_only=False)
    public = await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4, public_only=True)
    assert len(manager) == 3
    assert [item.origin_type for item in public] == ["series"]
    assert public[0].source_url is None
    assert public[0].url == "https://example.com/public.pdf"
    assert all(item.visibility == "public" for item in public)
    series = await CatalogDocumentService.get_workspace(document_session, target_type="series", target_id=3)
    assert series.own[0].source_url == "https://example.com/supplier-notes"
    product = await document_session.get(Product, 4)
    assert (await CatalogDocumentService.resolve_for_products(document_session, [product]))[4] == public


@pytest.mark.asyncio
async def test_owner_only_materials_do_not_inherit_and_unpublished_ancestors_stay_private(document_session):
    document_session.add_all([
        _document(brand_id=1, inherit_to_products=False, url="https://example.com/brand-only.pdf"),
        _document(series_id=3, inherit_to_products=False, url="https://example.com/series-only.pdf"),
        _document(brand_id=1, url="https://example.com/brand.pdf"),
        _document(series_id=3, url="https://example.com/series.pdf"),
    ])
    brand = await document_session.get(Brand, 1)
    brand.is_published = False
    document_session.add(brand)
    await document_session.commit()
    public = await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4)
    assert [item.url for item in public] == ["https://example.com/series.pdf"]
    series = await document_session.get(ProductSeries, 3)
    series.is_published = False
    document_session.add(series)
    await document_session.commit()
    assert await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4) == []
    manager = await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4, public_only=False)
    assert len(manager) == 2
    product = await document_session.get(Product, 4)
    product.is_published = False
    document_session.add(product)
    document_session.add(_document(product_id=4))
    await document_session.commit()
    assert await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4) == []


@pytest.mark.asyncio
async def test_batch_matches_single_resolution_and_populates_series_without_product_queries(document_session):
    document_session.add_all([
        _document(brand_id=1, url="https://example.com/catalog.pdf"),
        _document(series_id=3),
        _document(product_id=4, url="https://example.com/model.pdf"),
    ])
    await document_session.commit()
    products = list((await document_session.execute(select(Product).options(selectinload(Product.series)))).scalars())
    statements = []
    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(document_session.bind.sync_engine, "before_cursor_execute", record_statement)
    try:
        batch = await CatalogDocumentService.resolve_for_products(document_session, products)
    finally:
        event.remove(document_session.bind.sync_engine, "before_cursor_execute", record_statement)
    assert len(statements) == 3
    assert not any("FROM product \n" in statement for statement in statements)
    single = await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4)
    assert batch[4] == single
    assert [item.origin_type for item in batch[5]] == ["series", "brand"]
    series = await document_session.get(ProductSeries, 3)
    assert [item.origin_type for item in series.__dict__["_catalog_documents"]] == ["series", "brand"]


@pytest.mark.asyncio
async def test_inconsistent_series_brand_does_not_leak_reference(document_session):
    product = await document_session.get(Product, 4)
    product.brand_id = 2
    document_session.add(product)
    document_session.add(_document(series_id=3))
    document_session.add(_document(brand_id=1, url="https://example.com/brand.pdf"))
    await document_session.commit()
    assert await CatalogDocumentService.get_effective_documents(document_session, target_type="product", target_id=4) == []
    assert (await CatalogDocumentService.resolve_for_products(document_session, [product]))[4] == []


@pytest.mark.asyncio
async def test_replace_preserves_ids_and_semantic_noop_does_not_invalidate(document_session, monkeypatch):
    document = _document(series_id=3)
    document_session.add(document)
    await document_session.commit()
    async def commit(session, **kwargs):
        await session.commit()
    commit_mock = AsyncMock(side_effect=commit)
    monkeypatch.setattr(CatalogInvalidationCommitService, "commit_registered_global_mutation", commit_mock)
    payload = CatalogDocumentsReplacePayload(documents=[CatalogDocumentInput(
        title="Material", url="HTTPS://EXAMPLE.COM:443/manual.pdf#page=2", kind="operation",
    )])
    result = await CatalogDocumentService.replace_documents(document_session, target_type="series", target_id=3, payload=payload)
    assert result.own[0].id == document.id
    assert commit_mock.await_args.kwargs["changed"] is False
    payload.documents[0].title = "New manual title"
    result = await CatalogDocumentService.replace_documents(document_session, target_type="series", target_id=3, payload=payload)
    assert result.own[0].id == document.id
    assert result.own[0].title == "New manual title"
    assert commit_mock.await_args.kwargs["changed"] is True
    assert commit_mock.await_args.kwargs["producer"] == "catalog_documents.replace_documents"
    assert commit_mock.await_args.kwargs["brand_slugs"] == ["example"]


@pytest.mark.asyncio
async def test_failed_invalidation_can_roll_back_the_entire_change(document_session, monkeypatch):
    document_session.add(_document(series_id=3))
    await document_session.commit()
    monkeypatch.setattr(CatalogInvalidationCommitService, "commit_registered_global_mutation", AsyncMock(side_effect=RuntimeError("outbox failed")))
    with pytest.raises(RuntimeError, match="outbox failed"):
        await CatalogDocumentService.replace_documents(document_session, target_type="series", target_id=3, payload=CatalogDocumentsReplacePayload())
    await document_session.rollback()
    remaining = await CatalogDocumentService.get_workspace(document_session, target_type="series", target_id=3)
    assert len(remaining.own) == 1


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "javascript:alert(1)", "https://user:password@example.com/manual.pdf",
    "http://localhost/file.pdf", "http://127.0.0.1/file.pdf", "http://10.1.0.4/file.pdf",
    "http://169.254.169.254/file.pdf", "https://[::1]/file.pdf", "https://internal.lan/file.pdf",
    "https://example.com:8443/manual.pdf", "/media/../secret.pdf", "//example.com/manual.pdf",
    "http://2130706433/file.pdf", "http://127.1/file.pdf",
])
def test_rejects_private_unsafe_or_ambiguous_document_references(url):
    with pytest.raises(ValidationError):
        CatalogDocumentInput(title="Reference", url=url)


def test_validates_document_metadata_and_keeps_distinct_query_urls():
    first = CatalogDocumentInput(title="  Catalog  ", url="https://EXAMPLE.COM/catalog?year=2025#page=2", year=2025, language="ru-BY")
    second = CatalogDocumentInput(title="Catalog", url="https://example.com/catalog?year=2026")
    assert first.title == "Catalog"
    assert first.url == "https://example.com/catalog?year=2025"
    assert first.url != second.url
    with pytest.raises(ValidationError):
        CatalogDocumentInput(title="  ", url="https://example.com/catalog")
    with pytest.raises(ValidationError):
        CatalogDocumentInput(title="Catalog", url="https://example.com/catalog", year=1800)
    with pytest.raises(ValidationError):
        CatalogDocumentsReplacePayload(documents=[first] * 101)
