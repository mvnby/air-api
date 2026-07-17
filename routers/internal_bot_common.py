"""Small HTTP helpers shared by private Telegram bot routers."""

import json
from typing import Any

from fastapi import HTTPException, UploadFile, status

from api_contracts.bot import BOT_UPLOAD_MAX_FILE_SIZE_BYTES


async def read_bot_upload(file: UploadFile) -> tuple[bytes, str, str]:
    content = await file.read(BOT_UPLOAD_MAX_FILE_SIZE_BYTES + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )
    if len(content) > BOT_UPLOAD_MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded file exceeds the 10 MB limit",
        )
    filename = " ".join(str(file.filename or "telegram-file").split())[:160]
    mime_type = str(file.content_type or "application/octet-stream")[:160]
    return content, filename or "telegram-file", mime_type


def parse_json_object(value: str, *, field_name: str) -> dict[str, Any]:
    if len(value) > 100_000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} is too large",
        )
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a JSON object",
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be a JSON object",
        )
    return parsed
