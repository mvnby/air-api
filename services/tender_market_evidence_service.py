"""Queue and reuse bounded verification of public tender originals."""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_maker
from crud.tender_market import TenderMarketDAO
from crud.tender_market_evidence import TenderMarketEvidenceDAO
from models import TenderMarketEvidence, TenderMarketPublication
from models.tenancy import TenantScope
from schemas_manager_tender_evidence import ManagerTenderEvidenceReport
from schemas_tender_market import TenderMarketEvidenceResult
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.tender_document_reader import load_public_tender_original
from services.tender_market_service import TenderMarketService
from services.tender_market_source import market_original_inventory
from services.tender_market_sync_service import TenderMarketSyncService
from services.tender_module_service import TenderModuleError
from services.tender_original_evidence import TenderOriginalEvidence
from services.tender_qualification import qualify_tender_documents

_READER_VERSION = 2
_MAX_PENDING = 24
_MAX_FILES = 8
_MAX_ATTEMPTS = 2
_READ_SECONDS = 80
_ANALYSIS_SECONDS = 40
_LEASE = timedelta(seconds=_READ_SECONDS + _ANALYSIS_SECONDS + 30)
_RETRY_DELAY = timedelta(minutes=1)
_RETRY_AFTER_FAILURE = timedelta(minutes=5)
_RECHECK_AFTER_SUCCESS = timedelta(hours=24)
_SPECIFICATION = re.compile(r"\bтз\b|техническ\w*\s+задани|дефект|смет|спецификац", re.I)
_TRANSIENT_FILE_STATES = {"unavailable", "timeout", "unreadable"}
_SOURCE_ERROR = "Не удалось получить перечень оригиналов. Повторите проверку позже."
logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _current(row: TenderMarketEvidence, publication: TenderMarketPublication) -> bool:
    return row.reader_version == _READER_VERSION and _utc(row.source_revision) == _utc(publication.provider_updated_at)


def _finish_lease(row: TenderMarketEvidence) -> None:
    row.lease_token = None
    row.lease_until = None


def _reset(row: TenderMarketEvidence, publication: TenderMarketPublication, now: datetime) -> None:
    # Retain the previous completed report for exact-content reuse, even when
    # the publisher's metadata revision has changed.
    if row.reader_version != _READER_VERSION:
        row.fingerprint = None
    row.status = "queued"
    row.source_revision = publication.provider_updated_at
    row.reader_version = _READER_VERSION
    row.attempts = 0
    row.available_at = now
    row.error = None
    _finish_lease(row)


def _snapshot(row: TenderMarketEvidence | None, publication: TenderMarketPublication) -> TenderMarketEvidenceResult:
    if row is None or not _current(row, publication):
        return TenderMarketEvidenceResult(status="unrequested")
    return TenderMarketEvidenceResult(
        status=row.status, error=row.error,
        checked_at=_utc(row.checked_at) if row.checked_at and row.status == "completed" else None,
        report=ManagerTenderEvidenceReport.model_validate(row.report) if row.report and row.status == "completed" else None,
        documents_source_url=row.documents_source_url if row.status == "completed" else None,
    )


@dataclass(frozen=True)
class _Claim:
    publication: TenderMarketPublication
    token: str
    fingerprint: str | None
    cached_report: dict | None


@dataclass(frozen=True)
class _VerifiedReport:
    value: ManagerTenderEvidenceReport
    fingerprint: str | None
    source_url: str | None
    retryable: bool


class TenderMarketEvidenceService:
    @staticmethod
    async def get(session: AsyncSession, scope: TenantScope, publication_id: int) -> TenderMarketEvidenceResult:
        publication = await TenderMarketService.visible_publication(session, scope, publication_id)
        return _snapshot(await TenderMarketEvidenceDAO.get(session, publication_id), publication)

    @staticmethod
    async def request(session: AsyncSession, scope: TenantScope, publication_id: int) -> TenderMarketEvidenceResult:
        await TenderMarketDAO.checkpoint(session, lock=True)
        publication = await TenderMarketService.visible_publication(session, scope, publication_id)
        if not TenderMarketSyncService.enabled():
            raise TenderModuleError(503, "Проверка файлов станет доступна после подключения ленты.")
        row = await TenderMarketEvidenceDAO.get(session, publication_id)
        now = datetime.now(timezone.utc)
        if row is not None:
            if row.status in {"queued", "reading"}:
                return _snapshot(row, publication) if _current(row, publication) else TenderMarketEvidenceResult(status="queued")
            if _current(row, publication) and _utc(row.available_at) > now:
                return _snapshot(row, publication)
        if await TenderMarketEvidenceDAO.pending_count(session) >= _MAX_PENDING:
            raise TenderModuleError(429, "Очередь проверки заполнена. Повторите чуть позже.")
        if row is None:
            row = TenderMarketEvidence(
                publication_id=publication_id, source_revision=publication.provider_updated_at, reader_version=_READER_VERSION,
            )
        _reset(row, publication, now)
        session.add(row)
        result = _snapshot(row, publication)
        await session.commit()
        return result

    @staticmethod
    async def _claim() -> _Claim | None:
        async with async_session_maker() as session, session.begin():
            await TenderMarketDAO.checkpoint(session, lock=True)
            now = datetime.now(timezone.utc)
            if await TenderMarketEvidenceDAO.has_running(session, now):
                return None
            row = await TenderMarketEvidenceDAO.claimable(session, now)
            if row is None:
                return None
            publication = await TenderMarketDAO.get(session, row.publication_id)
            if publication is None or not publication.active:
                row.status, row.error = "failed", "Публикация недоступна у источника."
            else:
                if not _current(row, publication):
                    _reset(row, publication, now)
                if row.attempts < _MAX_ATTEMPTS:
                    row.status = "reading"
                    row.attempts += 1
                    row.lease_until = now + _LEASE
                    row.lease_token = uuid4().hex
                    session.expunge(publication)
                    return _Claim(publication, row.lease_token, row.fingerprint, row.report)
                row.status, row.error = "failed", _SOURCE_ERROR
            row.available_at = now + _RETRY_AFTER_FAILURE
            _finish_lease(row)
            return None

    @staticmethod
    async def _settle(claim: _Claim, report: _VerifiedReport | None) -> None:
        async with async_session_maker() as session, session.begin():
            await TenderMarketDAO.checkpoint(session, lock=True)
            row = await TenderMarketEvidenceDAO.get(session, claim.publication.id)
            now = datetime.now(timezone.utc)
            if row is None or row.lease_token != claim.token or row.lease_until is None or _utc(row.lease_until) <= now:
                return
            latest = await TenderMarketDAO.get(session, claim.publication.id)
            if latest is not None and latest.active and not _current(row, latest):
                _reset(row, latest, now)
                return
            _finish_lease(row)
            if report is None:
                retry = row.attempts < _MAX_ATTEMPTS and latest is not None and latest.active
                row.status, row.error = ("queued", None) if retry else ("failed", _SOURCE_ERROR)
                row.available_at = now + (_RETRY_DELAY if retry else _RETRY_AFTER_FAILURE)
                return
            row.status = "completed"
            row.checked_at = now
            row.available_at = now + (_RETRY_AFTER_FAILURE if report.retryable else _RECHECK_AFTER_SUCCESS)
            row.report = report.value.model_dump(mode="json")
            row.fingerprint = report.fingerprint
            row.documents_source_url = report.source_url

    @classmethod
    async def run_one(cls) -> None:
        claim = await cls._claim()
        if claim is None:
            return
        report = None
        try:
            report = await _verify(claim)
        except (TimeoutError, ValueError, RuntimeError, httpx.HTTPError) as error:
            logger.warning("Public tender originals unavailable publication_id=%s reason=%s",
                           claim.publication.id, type(error).__name__)
        await cls._settle(claim, report)


async def _verify(claim: _Claim) -> _VerifiedReport:
    clock = asyncio.get_running_loop().time
    started = clock()
    deadline = started + _READ_SECONDS
    async with asyncio.timeout_at(deadline):
        review = await market_original_inventory(claim.publication)
    if review.warning:
        raise ValueError(review.warning)

    originals = BelzakupkiEnrichmentService._documents(review.detail)
    inventory: dict[str, str] = {}
    duplicates: set[str] = set()
    for document in originals:
        identity = str(document["id"])
        if identity in inventory:
            duplicates.add(identity)
        if identity and len(identity) <= 300:
            inventory[identity] = str(document.get("name") or "Оригинал")[:500]
    selected = sorted(
        inventory.keys() - duplicates,
        key=lambda identity: (not _SPECIFICATION.search(inventory[identity]), identity),
    )[:_MAX_FILES]
    evidence = TenderOriginalEvidence(len(selected))
    for identity in selected:
        try:
            async with asyncio.timeout_at(deadline):
                original = await load_public_tender_original(claim.publication.id, identity, review)
        except TimeoutError:
            evidence.add_timeout(identity, inventory[identity])
        else:
            evidence.add(original, inventory[identity])
    unselected = len(originals) - len(selected)
    complete = not unselected and evidence.all_documents_complete and review.detail.get("document_inventory_complete") is True
    retryable = review.detail.get("document_inventory_complete") is not True or any(
        file.status in _TRANSIENT_FILE_STATES for file in evidence.documents
    )
    fingerprint = None
    if evidence.documents and not retryable and all(file.sha256 for file in evidence.documents):
        fingerprint = hashlib.sha256(json.dumps([
            review.document_identity, complete, unselected,
            [(file.document_id, file.sha256, file.filename, file.status) for file in evidence.documents],
        ], ensure_ascii=False).encode()).hexdigest()
    if fingerprint and fingerprint == claim.fingerprint and claim.cached_report:
        cached = ManagerTenderEvidenceReport.model_validate(claim.cached_report)
        return _VerifiedReport(cached, fingerprint, review.documents_source_url, False)

    analysis = await qualify_tender_documents(
        evidence.fragments, complete=complete, provider="deepseek", provider_timeout_seconds=_ANALYSIS_SECONDS,
    )
    logger.info("Public tender verification publication_id=%s files=%d seconds=%.2f analysis=%s",
                claim.publication.id, len(evidence.documents), clock() - started, analysis.extraction_status)
    return _VerifiedReport(
        ManagerTenderEvidenceReport(
            documents=evidence.documents, unselected_count=unselected, document_coverage_complete=complete,
            analysis_status=analysis.extraction_status, findings=[fact for fact in analysis.facts if fact.evidence],
        ),
        fingerprint if analysis.extraction_status == "completed" else None,
        review.documents_source_url, retryable or analysis.extraction_status == "local_evidence_only",
    )
