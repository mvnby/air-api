"""Durable observation of primary decisions; never writes CRM decisions."""
import asyncio
import hashlib
import json
import logging
from statistics import median

from sqlalchemy.exc import IntegrityError

from core.database import async_session_maker
from crud import jev_shadow as dao
from models.jev_shadow import JevConnection, JevShadowSample
from services.jev_connection_service import JevConnectionService, JevCredentialCipher, MAX_DAILY_REQUESTS
from services.jev_provider_service import classify_jev, JevProviderError

logger = logging.getLogger(__name__)
PROMPT_VERSION = "intake-v1"


class JevShadowService:
    @classmethod
    async def enqueue(cls, *, tenant_scope, source, identity, subject, body, primary_provider,
                      primary_model_requested=None, primary_is_relevant=None, primary_duration_ms=None):
        """Independent commit also retains rejected emails which create no CRM row."""
        if not tenant_scope.is_system:
            return
        sample = cls._sample(tenant_scope=tenant_scope, source=source, identity=identity, subject=subject,
            body=body, primary_provider=primary_provider, primary_model_requested=primary_model_requested,
            primary_is_relevant=primary_is_relevant, primary_duration_ms=primary_duration_ms)
        await cls._enqueue_samples(tenant_scope=tenant_scope, samples=[sample])

    @staticmethod
    def _sample(*, tenant_scope, source, identity, subject, body, primary_provider,
                primary_model_requested=None, primary_is_relevant=None, primary_duration_ms=None):
        clean_subject = " ".join(str(subject or "").replace("\xa0", " ").split())[:500]
        clean_body = " ".join(str(body or "").replace("\xa0", " ").split())[:5000]
        state = f"Subject: {clean_subject}\nBody: {clean_body}"
        digest = hashlib.sha256(json.dumps([identity, state, PROMPT_VERSION], ensure_ascii=False).encode()).hexdigest()
        return JevShadowSample(tenant_id=tenant_scope.tenant_id, storefront_id=tenant_scope.storefront_id,
            source=source, sample_key=digest, subject=clean_subject, state=state, prompt_version=PROMPT_VERSION,
            primary_provider=primary_provider, primary_model_requested=primary_model_requested,
            primary_is_relevant=primary_is_relevant, primary_duration_ms=primary_duration_ms)

    @classmethod
    async def _enqueue_samples(cls, *, tenant_scope, samples):
        if not tenant_scope.is_system or not samples:
            return
        try:
            # Short DB-only deadline; no provider request belongs in an intake transaction.
            async with asyncio.timeout(2):
                async with async_session_maker() as session:
                    async with session.begin():
                        connection = await JevConnectionService.get(session, for_update=True)
                        if not connection or not connection.enabled or not connection.encrypted_credentials:
                            return
                        if not await dao.is_system_tenant(session, tenant_scope.tenant_id):
                            return
                        capacity = dao.MAX_PENDING - await dao.pending_count(session)
                        for sample in samples:
                            if capacity <= 0:
                                break
                            if await dao.sample_exists(session, tenant_id=sample.tenant_id, storefront_id=sample.storefront_id,
                                                       source=sample.source, sample_key=sample.sample_key):
                                continue
                            session.add(sample)
                            await session.flush()
                            capacity -= 1
        except IntegrityError:
            # A concurrent replay inserted the same sample. It must not spend again.
            pass
        except Exception:
            logger.warning("JEV_SHADOW enqueue_failed")

    @classmethod
    async def enqueue_tenders(cls, *, tenant_scope, items):
        if not tenant_scope.is_system:
            return
        samples = []
        for item in items:
            tender = item.get("tender") or {}
            if not tender.get("source") or not tender.get("external_id"):
                continue
            identity = [tender.get("source"), tender.get("external_id"), (item.get("profile") or {}).get("id")]
            relevance = item.get("relevance_status")
            # Eligibility/deadlines and keyword-only matches are not AI judgments.
            primary = True if relevance == "confirmed" else False if relevance == "rejected" else None
            samples.append(cls._sample(tenant_scope=tenant_scope, source="belzakupki", identity=identity,
                subject=tender.get("title"), body=tender.get("summary"), primary_provider="belzakupki",
                primary_is_relevant=primary))
        await cls._enqueue_samples(tenant_scope=tenant_scope, samples=samples)

    @classmethod
    async def process_one(cls):
        async with async_session_maker() as session:
            async with session.begin():
                claimed = await dao.claim_next(session, max_daily_requests=MAX_DAILY_REQUESTS)
                if claimed is None:
                    return False
                connection, sample = claimed
                sample_id, state = sample.id, sample.state
                token = JevCredentialCipher.decrypt_with_source(connection.encrypted_credentials)[0]
        result, error_code = None, None
        try:
            result = await classify_jev(token=token, state=state)
        except JevProviderError as exc:
            error_code = exc.code
        except Exception:
            error_code = "provider_error"
        # Do not keep the DB connection or transaction open during inference.
        async with async_session_maker() as session:
            async with session.begin():
                connection = await session.get(JevConnection, 1, with_for_update=True)
                sample = await session.get(JevShadowSample, sample_id, with_for_update=True)
                if not sample or sample.status != "running":
                    return True
                if result:
                    sample.status, sample.model = "completed", result.model
                    sample.kind, sample.kind_confidence = result.kind, result.kind_confidence
                    sample.hvac_probability, sample.jev_is_relevant = result.hvac_probability, result.is_potential_order
                    sample.input_tokens, sample.duration_ms = result.input_tokens, result.duration_ms
                    sample.estimated_usd = result.estimated_usd
                    if connection and connection.budget_day == sample.budget_day:
                        connection.budget_used_usd += result.estimated_usd - dao.RESERVATION_USD
                else:
                    sample.status, sample.error_code = "failed", error_code
                    # On failure we cannot know the provider's billed tokens.
                    # Keep the worst-case reservation instead of understating spend.
                session.add(sample)
                if connection:
                    session.add(connection)
        return True

    @classmethod
    async def process_batch(cls):
        # One scheduler on the writable primary; row locks also fence overlap.
        return sum(await asyncio.gather(*(cls.process_one() for _ in range(4))))

    @classmethod
    async def report(cls, session, *, tenant_id, source=None, disagreements_only=False, limit=20):
        counts = await dao.status_counts(session, tenant_id=tenant_id, source=source)
        aggregate, comparable, agreements, durations = await dao.completed_metrics(session, tenant_id=tenant_id, source=source)
        rows = await dao.report_items(session, tenant_id=tenant_id, source=source, disagreements_only=disagreements_only, limit=limit)
        names = ("id", "source", "subject", "state", "created_at", "status", "primary_provider", "primary_model_requested",
                 "primary_is_relevant", "primary_duration_ms", "model", "kind", "kind_confidence", "hvac_probability", "jev_is_relevant", "duration_ms", "input_tokens", "estimated_usd", "error_code")
        return {**{name: counts.get(name, 0) for name in ("queued", "running", "completed", "failed")},
                "comparable": comparable, "agreements": agreements, "disagreements": comparable - agreements,
                "estimated_usd": aggregate[0], "input_tokens": aggregate[1],
                "median_duration_ms": median(durations) if durations else None,
                "items": [{name: getattr(row, name) for name in names} for row in rows]}
