"""Company/site selection for the staff bot (never virtual operator access)."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.bot import (
    BotStaffContextResponse,
    BotStaffContextChoicesResponse,
    BotStaffContextSelectRequest,
)
from core.bot_api_security import require_bot_api_token
from core.database import get_session
from services.bot_access_service import BotAccessService
from services.bot_staff_selection_service import BotStaffSelectionService

router = APIRouter(
    prefix="/api/internal/bot/v1",
    tags=["internal bot v1"],
    dependencies=[Depends(require_bot_api_token)],
)


def context_response(context) -> BotStaffContextResponse:
    selection = context.selection
    fields = (
        {
            name: getattr(selection, name)
            for name in (
                "staff_user_id",
                "tenant_id",
                "storefront_id",
                "tenant_slug",
                "tenant_name",
                "storefront_slug",
                "storefront_name",
                "context_version",
                "can_switch_context",
            )
        }
        if selection
        else {}
    )
    if context.selection_unavailable:
        for key in (
            "tenant_id",
            "storefront_id",
            "tenant_slug",
            "tenant_name",
            "storefront_slug",
            "storefront_name",
        ):
            fields[key] = None
    return BotStaffContextResponse(
        telegram_id=context.telegram_id,
        is_staff=context.is_staff,
        display_name=context.display_name,
        primary_role=context.primary_role,
        roles=context.roles,
        legacy_installer_id=context.legacy_installer_id,
        is_manager=context.is_manager,
        is_executor=context.is_executor,
        **fields,
    )


@router.get(
    "/staff/context/{telegram_id}/choices",
    response_model=BotStaffContextChoicesResponse,
    operation_id="get_internal_bot_staff_context_choices_v1",
)
async def choices(
    telegram_id: int = Path(gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """List a deterministic page of at most 100 accessible company/site pairs.

    Access: service BOT_API_TOKEN plus an active linked staff identity and real active
    memberships. An invalid previous selection does not prevent choosing again.
    """
    context = await BotAccessService.get_context(
        session, telegram_id, ignore_selection=True
    )
    if not context.is_staff or context.selection is None:
        raise HTTPException(403, "Active staff membership is required")
    rows = await BotStaffSelectionService.rows(session, context.staff_user_id)
    grouped = {}
    for member, tenant, site in rows[offset : offset + limit]:
        company = grouped.setdefault(
            int(tenant.id),
            dict(
                tenant_id=int(tenant.id),
                tenant_slug=tenant.slug,
                tenant_name=tenant.display_name,
                primary_role=member.role,
                permissions=member.permissions or [],
                storefronts=[],
            ),
        )
        company["storefronts"].append(
            dict(
                storefront_id=int(site.id),
                storefront_slug=site.slug,
                storefront_name=site.display_name,
                is_default=site.is_default,
            )
        )
    return BotStaffContextChoicesResponse(
        context_version=context.selection.context_version,
        choices=list(grouped.values()),
        offset=offset,
        limit=limit,
        total=len(rows),
    )


@router.post(
    "/staff/context/select",
    response_model=BotStaffContextResponse,
    operation_id="select_internal_bot_staff_context_v1",
)
async def select_context(
    payload: BotStaffContextSelectRequest, session: AsyncSession = Depends(get_session)
):
    """Select an accessible company/site using optimistic context concurrency.

    Access: service BOT_API_TOKEN and the actor's real active membership; no platform
    owner virtual access or caller-provided role grants. A stale version returns 409.
    """
    context = await BotAccessService.get_context(
        session, payload.telegram_id, ignore_selection=True
    )
    if not context.is_staff or context.selection is None:
        raise HTTPException(403, "Active staff membership is required")
    await BotStaffSelectionService.select(
        session,
        context.selection,
        tenant_id=payload.tenant_id,
        storefront_slug=payload.storefront_slug,
        expected_version=payload.expected_context_version,
    )
    return context_response(
        await BotAccessService.get_context(session, payload.telegram_id)
    )
