"""Explicitly assigned work rendered through the safe installer projection."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from models.tenancy import TenantScope
from services.bot_task_service import BotTaskService
from services.bot_worker_access import BotWorkerAccessDeniedError, bot_worker_context
from services.worker_assignment_service import WorkerAssignmentError
from services.installer_collection_service import InstallerWorkspaceError
from services.installer_work_urls import installer_work_url


class BotTaskAccessDeniedError(PermissionError):
    """The Telegram identity cannot use staff task scenarios."""


class BotTaskReadService:
    @staticmethod
    async def list_for_staff(
        session: AsyncSession,
        *,
        telegram_id: int,
        limit: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        statuses: list[str] | None = None,
        tenant_scope: TenantScope,
    ) -> list[dict]:
        from services.installer_workspace_service import InstallerWorkspaceService

        try:
            auth, selection = await bot_worker_context(session, telegram_id, tenant_scope)
            safe_limit = max(1, min(int(limit or 10), 20))
            start = BotTaskService._normalize_filter_datetime(date_from) or datetime.now() - timedelta(days=1)
            end = BotTaskService._normalize_filter_datetime(date_to) or datetime.now() + timedelta(days=30)
            requested = set(statuses or [])
            result = []
            page = 1
            while len(result) < safe_limit:
                works = await InstallerWorkspaceService.list_works(session, auth, page=page, limit=100, bucket="all")
                for summary in works.items:
                    when = BotTaskService._normalize_filter_datetime(summary.start_time)
                    if (requested and summary.status not in requested) or (when is not None and not start <= when <= end):
                        continue
                    detail = await InstallerWorkspaceService.detail(session, auth, summary.id)
                    url = installer_work_url(detail.id, tenant_id=tenant_scope.tenant_id, storefront_slug=selection.storefront_slug)
                    result.append({
                        "kind": "stage" if detail.work_stage_id is not None else "order",
                        "id": detail.work_stage_id or detail.order_id, "order_id": detail.order_id,
                        "stage_id": detail.work_stage_id, "title": detail.title, "status": detail.status,
                        "start_time": detail.start_time, "address": detail.address,
                        "customer_name": detail.customer_name, "customer_phone": detail.customer_phone,
                        "comment": detail.instructions or None, "manager_url": None, "work_url": url,
                    })
                    if len(result) >= safe_limit:
                        break
                if not works.items or page * 100 >= works.total:
                    break
                page += 1
            result.sort(key=lambda item: (item["start_time"] is None, item["start_time"] or datetime.max, item["id"]))
            return result
        except (BotWorkerAccessDeniedError, WorkerAssignmentError, InstallerWorkspaceError) as exc:
            raise BotTaskAccessDeniedError(str(exc)) from exc
