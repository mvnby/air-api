import asyncio

import pytest

from schemas_contract_review import ContractReviewResponse
from services.email_contract_review_job_service import EmailContractReviewJobService


@pytest.mark.asyncio
async def test_review_job_is_private_and_completes_without_request_wait(monkeypatch):
    EmailContractReviewJobService._jobs.clear()
    release = asyncio.Event()

    async def review_content(*, attachment_id, filename, content):
        await release.wait()
        assert content == b"private contract"
        return ContractReviewResponse(
            attachment_id=attachment_id, filename=filename, content_sha256="digest",
            model="deepseek-v4-pro", pages=None, risks=[], note="manual review",
        )

    monkeypatch.setattr(
        "services.email_contract_review_job_service.EmailContractReviewService.review_content",
        review_content,
    )
    started = await EmailContractReviewJobService.start(
        owner="tenant-a:manager", attachment_id=7,
        filename="contract.doc", content=b"private contract",
    )

    assert started.status == "running"
    assert await EmailContractReviewJobService.get(job_id=started.job_id, owner="tenant-b:manager") is None
    release.set()
    for _ in range(10):
        await asyncio.sleep(0)
        current = await EmailContractReviewJobService.get(job_id=started.job_id, owner="tenant-a:manager")
        if current and current.status == "completed":
            break
    assert current is not None and current.status == "completed"
    assert current.report is not None and current.report.filename == "contract.doc"
    EmailContractReviewJobService._jobs.clear()
