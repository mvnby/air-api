from fastapi import APIRouter, Depends, HTTPException
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
    dependencies=[Depends(get_current_username)],
)


@router.get("/status", response_model=ManagerGoogleAuthStatusResponse, operation_id=GET_MANAGER_GOOGLE_AUTH_STATUS)
async def get_manager_google_auth_status():
    status_payload = get_google_service().get_token_status()
    return ManagerGoogleAuthStatusResponse(**status_payload)


@router.get("/url", response_model=ManagerGoogleAuthUrlResponse, operation_id=GET_MANAGER_GOOGLE_AUTH_URL)
async def get_manager_google_auth_url():
    try:
        url = get_google_service().get_auth_url()
        return ManagerGoogleAuthUrlResponse(url=url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/exchange", response_model=ManagerActionMessageResponse, operation_id=EXCHANGE_MANAGER_GOOGLE_AUTH_CODE)
async def exchange_manager_google_auth_code(payload: ManagerGoogleAuthExchangePayload):
    code = (payload.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Google auth code is required")

    try:
        get_google_service().finish_auth(code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ManagerActionMessageResponse(message="Google authentication updated successfully")
