from html import escape

import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.security import get_current_username
from routers.manager_operation_ids import (
    EXCHANGE_MANAGER_GOOGLE_AUTH_CODE,
    GET_MANAGER_GOOGLE_AUTH_STATUS,
    GET_MANAGER_GOOGLE_AUTH_URL,
)
from schemas import ManagerActionMessageResponse, ManagerGoogleAuthStatusResponse, ManagerGoogleAuthUrlResponse
from services.google_service import get_google_service


class ManagerGoogleAuthExchangePayload(BaseModel):
    code: str


router = APIRouter(
    prefix="/api/manager/google-auth",
    tags=["manager/google-auth"],
)


def _google_oauth_redirect_uri(request: Request) -> str:
    configured = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if configured:
        return configured
    return str(request.url_for("manager_google_auth_callback"))


@router.get("/status", response_model=ManagerGoogleAuthStatusResponse, operation_id=GET_MANAGER_GOOGLE_AUTH_STATUS)
async def get_manager_google_auth_status(_: str = Depends(get_current_username)):
    status_payload = await run_in_threadpool(lambda: get_google_service().get_token_status())
    return ManagerGoogleAuthStatusResponse(**status_payload)


@router.get("/url", response_model=ManagerGoogleAuthUrlResponse, operation_id=GET_MANAGER_GOOGLE_AUTH_URL)
async def get_manager_google_auth_url(request: Request, _: str = Depends(get_current_username)):
    try:
        redirect_uri = _google_oauth_redirect_uri(request)
        url = await run_in_threadpool(lambda: get_google_service().get_auth_url(redirect_uri))
        return ManagerGoogleAuthUrlResponse(url=url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/exchange", response_model=ManagerActionMessageResponse, operation_id=EXCHANGE_MANAGER_GOOGLE_AUTH_CODE)
async def exchange_manager_google_auth_code(
    payload: ManagerGoogleAuthExchangePayload,
    request: Request,
    _: str = Depends(get_current_username),
):
    code = (payload.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Google auth code is required")

    try:
        redirect_uri = _google_oauth_redirect_uri(request)
        await run_in_threadpool(lambda: get_google_service().finish_auth(code, redirect_uri))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ManagerActionMessageResponse(message="Google authentication updated successfully")


@router.get("/callback", include_in_schema=False)
async def manager_google_auth_callback(request: Request, code: str = "", error: str = ""):
    if error:
        return HTMLResponse(
            content=f"""
            <html><body>
                <h1>Google authentication failed</h1>
                <p>{escape(error)}</p>
                <p><a href="/manager/settings">Back to manager settings</a></p>
            </body></html>
            """,
            status_code=400,
        )

    code = (code or "").strip()
    if not code:
        return HTMLResponse(
            content="""
            <html><body>
                <h1>Google authentication failed</h1>
                <p>Authorization code is missing.</p>
                <p><a href="/manager/settings">Back to manager settings</a></p>
            </body></html>
            """,
            status_code=400,
        )

    try:
        redirect_uri = _google_oauth_redirect_uri(request)
        await run_in_threadpool(lambda: get_google_service().finish_auth(code, redirect_uri))
    except Exception as exc:
        return HTMLResponse(
            content=f"""
            <html><body>
                <h1>Google authentication failed</h1>
                <p>{escape(str(exc))}</p>
                <p><a href="/manager/settings">Back to manager settings</a></p>
            </body></html>
            """,
            status_code=500,
        )

    return HTMLResponse(
        content="""
        <html><body>
            <h1>Google authentication updated</h1>
            <p>You can close this tab and return to manager settings.</p>
            <p><a href="/manager/settings">Back to manager settings</a></p>
        </body></html>
        """
    )
