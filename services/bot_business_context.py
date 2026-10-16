"""Capture request context once and check the issued version at write boundaries."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from services.bot_access_service import BotAccessService
from services.bot_staff_selection_service import BotStaffSelectionService


async def resolve_bot_scope(session: AsyncSession, telegram_id: int):
    context = await BotAccessService.get_context(session, telegram_id)
    if not context.is_staff or context.selection is None:
        raise HTTPException(403, "Выбранная компания или витрина недоступна")
    return context.selection.scope


async def bind_bot_business_context(
    request: Request, session: AsyncSession = Depends(get_session)
):
    path = request.url.path
    if path.endswith("/health") or "/staff/context" in path:
        yield
        return
    values = dict(request.query_params)
    if request.method != "GET":
        if request.headers.get("content-type", "").startswith("application/json"):
            body = await request.json()
            if isinstance(body, dict):
                values.update(body)
        elif "multipart/form-data" in request.headers.get("content-type", ""):
            values.update(await request.form())
    try:
        telegram_id = int(values.get("telegram_id", 0))
        expected = values.get("expected_context_version")
        expected = int(expected) if expected is not None else None
        if expected is not None and expected < 0:
            raise ValueError()
    except (TypeError, ValueError):
        raise HTTPException(422, "Invalid bot context version")
    if not telegram_id:
        yield
        return  # Endpoint DTO validation supplies its normal 422.
    context = await BotAccessService.get_context(session, telegram_id)
    if not context.is_staff:
        raise HTTPException(403, "Active staff membership is required")
    read_paths = (
        "/catalog/search",
        "/catalog/selection",
        "/catalog/curated",
        "/tasks/my",
        "/orders/recent",
        "/repair-nameplates/orders",
        "/warranty-nameplates/orders",
        "/quick-orders/customers/search",
        "/repair-context/comment-draft",
        "/repair-context/preset-draft",
    )
    mutation = request.method != "GET" and not path.endswith(read_paths)
    if context.selection is not None:
        await BotStaffSelectionService.bind_request(
            session, context.selection, expected, mutation=mutation
        )
    try:
        yield
        await BotStaffSelectionService.revalidate(session)
    except BaseException:
        await session.rollback()
        raise


async def get_bot_request_scope(session: AsyncSession = Depends(get_session)):
    selection = session.info.get("bot_selection")
    if selection is not None:
        return selection.scope
    raise HTTPException(403, "A selected staff company/site is required")
