"""Short-lived Manager jobs for reading and verifying original tender files."""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import uuid4

import httpx

from core.database import async_session_maker
from models.tenancy import TenantScope
from schemas_manager_tender_evidence import ManagerTenderEvidenceJob, ManagerTenderEvidenceReport
from schemas_tender_qualification import TenderQualificationResult
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.belzakupki_source_analysis import TenderAnalysisBusy
from services.tender_document_reader import load_tender_document
from services.tender_original_evidence import TenderOriginalEvidence
from services.tender_qualification import qualify_tender_documents
from services.tender_source_reference import source_for_manager_review

_MAX_ACTIVE_JOBS = 2
_MAX_RECENT_JOBS = 24
_TTL_SECONDS = 30 * 60
_READ_TIMEOUT_SECONDS = 80
_ANALYSIS_TIMEOUT_SECONDS = 40
_ACTIVE_STATUSES = {"reading", "analyzing"}
_RETRYABLE_FILE_STATUSES = {"timeout", "unavailable", "unreadable"}
logger = logging.getLogger(__name__)
_ScopeKey = tuple[int, int, int]
_AnalysisKey = tuple[
    _ScopeKey, tuple[str, str], bool, tuple[tuple[str, str | None, str | None, str | None, str], ...],
]


@dataclass
class _Job:
    scope_key: _ScopeKey
    document_ids: tuple[str, ...]
    updated_at: float
    snapshot: ManagerTenderEvidenceJob
    task: asyncio.Task[None] | None = None

    @property
    def active(self) -> bool:
        return self.snapshot.status in _ACTIVE_STATUSES


class ManagerTenderEvidenceService:
    _jobs: dict[str, _Job] = {}
    _analyses: OrderedDict[_AnalysisKey, tuple[float, TenderQualificationResult]] = OrderedDict()

    @staticmethod
    def _scope_key(scope: TenantScope, order_id: int) -> _ScopeKey:
        return scope.tenant_id, scope.storefront_id, order_id

    @classmethod
    def start(cls, *, order_id: int, scope: TenantScope, document_ids: list[str]) -> ManagerTenderEvidenceJob:
        scope_key = cls._scope_key(scope, order_id)
        selection = tuple(sorted(set(document_ids)))
        now = time.monotonic()
        active = []
        finished = []
        for job_id, job in list(cls._jobs.items()):
            if job.active:
                if job.scope_key == scope_key and job.document_ids == selection:
                    return job.snapshot.model_copy()
                active.append(job)
            elif now - job.updated_at >= _TTL_SECONDS:
                cls._jobs.pop(job_id)
            else:
                finished.append(job)
        if len(active) >= _MAX_ACTIVE_JOBS:
            raise TenderAnalysisBusy("Сейчас выполняются две проверки оригиналов. Повторите чуть позже.")
        if len(cls._jobs) >= _MAX_RECENT_JOBS:
            oldest = min(finished, key=lambda job: job.updated_at)
            cls._jobs.pop(oldest.snapshot.job_id)
        job_id = uuid4().hex
        snapshot = ManagerTenderEvidenceJob(job_id=job_id, status="reading", processed=0, total=len(selection))
        job = _Job(scope_key=scope_key, document_ids=selection, updated_at=now, snapshot=snapshot)
        cls._jobs[job_id] = job
        job.task = asyncio.create_task(cls._run(job, order_id, scope))
        return snapshot.model_copy()

    @classmethod
    def get(cls, *, order_id: int, scope: TenantScope, job_id: str) -> ManagerTenderEvidenceJob | None:
        job = cls._jobs.get(job_id)
        if job is None or job.scope_key != cls._scope_key(scope, order_id):
            return None
        if not job.active and time.monotonic() - job.updated_at >= _TTL_SECONDS:
            cls._jobs.pop(job_id)
            return None
        return job.snapshot.model_copy()

    @classmethod
    async def _run(cls, job: _Job, order_id: int, scope: TenantScope) -> None:
        try:
            report = await cls._report(job, order_id, scope)
            job.snapshot.status = "completed"
            job.snapshot.report = report
        except (TimeoutError, httpx.HTTPError, _InventoryUnavailable):
            job.snapshot.status = "failed"
            job.snapshot.error = "Источник оригиналов временно недоступен. Повторите проверку."
        except _InventoryChanged:
            job.snapshot.status = "failed"
            job.snapshot.error = "Перечень оригиналов изменился. Откройте карточку источника заново."
        except asyncio.CancelledError:
            job.snapshot.status = "failed"
            job.snapshot.error = "Не удалось проверить оригиналы. Повторите проверку."
            raise
        except Exception as error:
            logger.warning("Manager tender evidence job failed: %s", type(error).__name__)
            job.snapshot.status = "failed"
            job.snapshot.error = "Не удалось проверить оригиналы. Повторите проверку."
        finally:
            job.updated_at = time.monotonic()
            job.task = None

    @classmethod
    async def _report(cls, job: _Job, order_id: int, scope: TenantScope) -> ManagerTenderEvidenceReport:
        clock = asyncio.get_running_loop().time
        started = clock()
        deadline = started + _READ_TIMEOUT_SECONDS
        async with asyncio.timeout_at(deadline):
            async with async_session_maker() as session:
                order = await BelzakupkiEnrichmentService._order(session, order_id, scope)
            review = await source_for_manager_review(order)
        if review.warning:
            raise _InventoryUnavailable
        rows = BelzakupkiEnrichmentService._documents(review.detail)
        inventory = {str(row["id"]): str(row.get("name") or "Оригинал")[:500] for row in rows}
        if any(document_id not in inventory for document_id in job.document_ids):
            raise _InventoryChanged
        evidence = TenderOriginalEvidence()
        for document_id in job.document_ids:
            try:
                async with asyncio.timeout_at(deadline), async_session_maker() as session:
                    original = await load_tender_document(
                        session, scope, order_id=order_id, document_id=document_id, review=review,
                    )
            except TimeoutError:
                evidence.add_timeout(document_id, inventory[document_id])
            else:
                evidence.add(original, inventory[document_id])
            job.snapshot.processed += 1
        unselected = len(inventory) - len(job.document_ids)
        coverage = (
            unselected == 0 and evidence.all_documents_complete
            and len(rows) == len(inventory) == len(review.detail["documents"])
            and review.detail.get("document_inventory_complete") is not False
        )
        job.snapshot.status = "analyzing"
        key = None
        if all(file.sha256 and file.status not in _RETRYABLE_FILE_STATUSES for file in evidence.documents):
            key = (job.scope_key, review.document_identity, coverage, tuple(
                (file.document_id, file.filename, file.sha256, file.origin, file.status) for file in evidence.documents
            ))
        read_seconds = clock() - started
        analysis, reused = await cls._analyze(evidence, coverage, key)
        logger.info(
            "Manager tender verification files=%d fragments=%d read_seconds=%.2f total_seconds=%.2f ai=%s reused=%s",
            len(evidence.documents), len(evidence.fragments), read_seconds, clock() - started,
            analysis.extraction_status, reused,
        )
        return ManagerTenderEvidenceReport(
            documents=evidence.documents, unselected_count=unselected, document_coverage_complete=coverage,
            analysis_status=analysis.extraction_status, findings=[fact for fact in analysis.facts if fact.evidence],
        )

    @classmethod
    async def _analyze(
        cls, evidence: TenderOriginalEvidence, coverage: bool, key: _AnalysisKey | None,
    ) -> tuple[TenderQualificationResult, bool]:
        if key is not None:
            cached = cls._analyses.get(key)
            if cached and cached[0] > time.monotonic():
                cls._analyses.move_to_end(key)
                return cached[1], True
            cls._analyses.pop(key, None)
        analysis = await qualify_tender_documents(
            evidence.fragments, complete=coverage, provider="deepseek", provider_timeout_seconds=_ANALYSIS_TIMEOUT_SECONDS,
        )
        if key is not None and analysis.extraction_status == "completed":
            cls._analyses[key] = (time.monotonic() + _TTL_SECONDS, analysis)
            if len(cls._analyses) > _MAX_RECENT_JOBS:
                cls._analyses.popitem(last=False)
        return analysis, False


class _InventoryUnavailable(RuntimeError):
    """The mirror could not be matched to a current source inventory."""


class _InventoryChanged(ValueError):
    """The latest verified source inventory no longer contains a selected original."""
