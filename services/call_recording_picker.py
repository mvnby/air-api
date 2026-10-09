"""Browse folder metadata by the original Samsung call clock, without queuing work."""

import re
from datetime import date, datetime, timezone

from schemas_call_recordings import CallDriveFileListResponse, CallDriveFileResponse
from services.call_drive_connection_service import CallDriveConnectionService, require_live_call_actor
from services.call_drive_provider import CallDriveError, FILE_ID_PATTERN
from services.call_recording_structure import samsung_call_time

MAX_EMPTY_PAGES = 5
CALL_SUFFIX = re.compile(r"_\d{6}_\d{6}$")
CALL_PREFIX = re.compile(r"^(?:Запись вызова|Запись звонка|Вызов|Call recording|Voice call|Call)\s+", re.I)
PHONE_LABEL = re.compile(r"\+?[\d\s().-]+")


def project_file(metadata: dict, folder_id: str) -> CallDriveFileResponse | None:
    file_id = metadata.get("id")
    mime = str(metadata.get("mimeType") or "").lower()
    if (not isinstance(file_id, str) or not FILE_ID_PATTERN.fullmatch(file_id)
            or metadata.get("trashed") or folder_id not in metadata.get("parents", [])
            or not (mime.startswith("audio/") or mime in {"video/3gpp", "video/mp4", "application/ogg"})):
        return None
    filename = str(metadata.get("name") or "")
    call_time = samsung_call_time(filename)
    label = CALL_PREFIX.sub("", CALL_SUFFIX.sub("", filename.rsplit(".", 1)[0])).strip()
    digits = re.sub(r"\D", "", label)
    is_phone = bool(PHONE_LABEL.fullmatch(label) and 7 <= len(digits) <= 15)
    try:
        size = int(metadata["size"])
        if size < 0:
            size = None
    except (KeyError, ValueError, TypeError):
        size = None
    return CallDriveFileResponse(
        file_id=file_id, filename=filename[:300],
        source_url=f"https://drive.google.com/file/d/{file_id}/view",
        call_occurred_at=call_time, contact=label[:300] if label and not is_phone else None,
        phone=("+" if label.startswith("+") else "") + digits if is_phone else None,
        size=size,
    )


def matches_file(item: CallDriveFileResponse, *, date_from: date | None, date_to: date | None, query: str) -> bool:
    # Never substitute Drive modifiedTime for the date of the conversation.
    call_date = item.call_occurred_at.date() if item.call_occurred_at else None
    if date_from and (call_date is None or call_date < date_from):
        return False
    if date_to and (call_date is None or call_date > date_to):
        return False
    if not query:
        return True
    if query.casefold() in (item.contact or item.phone or "").casefold():
        return True
    query_digits = re.sub(r"\D", "", query)
    return bool(item.phone and PHONE_LABEL.fullmatch(query) and query_digits and query_digits in re.sub(r"\D", "", item.phone))


class CallRecordingPicker:
    @staticmethod
    async def list_files(session, actor, *, date_from=None, date_to=None, query="", page_token=None, provider=None):
        await require_live_call_actor(session, actor)
        if date_from and date_to and date_from > date_to:
            raise ValueError("Начало периода должно быть не позднее конца")
        adapter = await CallDriveConnectionService.adapter(session, actor, provider=provider)
        connection = await CallDriveConnectionService.get(session, actor)
        folder_id = connection.folder_id
        if not folder_id:
            raise CallDriveError("call_folder_not_selected", "Выберите папку с записями", status_code=409)
        items, token = [], page_token
        # Google name 'contains' is prefix-only; filter parsed labels locally to
        # avoid missing names/dates in the middle of Samsung filenames. Each
        # request is bounded and offers continuation instead of claiming completeness.
        for _ in range(MAX_EMPTY_PAGES):
            files, next_token = await adapter.list_recordings(folder_id, page_token=token, page_size=100)
            for metadata in files[:100]:
                item = project_file(metadata, folder_id)
                if item and matches_file(item, date_from=date_from, date_to=date_to, query=query.strip()):
                    items.append(item)
            if next_token and next_token == token:
                raise CallDriveError("call_drive_invalid_page", "Не удалось продолжить список записей", status_code=502)
            token = next_token
            if items or not token:
                break
        await require_live_call_actor(session, actor)
        current = await CallDriveConnectionService.get(session, actor)
        if current.folder_id != folder_id:
            raise CallDriveError("call_folder_changed", "Папка изменилась, повторите поиск", status_code=409)
        items.sort(key=lambda item: (item.call_occurred_at or datetime.min.replace(tzinfo=timezone.utc), item.filename), reverse=True)
        return CallDriveFileListResponse(items=items, next_page_token=token)
