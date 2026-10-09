from datetime import date

import httpx
import pytest

from services.call_drive_provider import GoogleCallDriveAdapter
from services.call_recording_picker import matches_file, project_file

FOLDER = "chosen-folder-00000001"


def metadata(name):
    return {"id": "safe-file-00000001", "name": name, "parents": [FOLDER],
            "mimeType": "video/3gpp", "size": "1024", "modifiedTime": "2026-10-09T23:30:00Z"}


@pytest.mark.parametrize("name,contact,phone", [
    ("Вызов Дима Кондиционерщик_261008_170514.m4a", "Дима Кондиционерщик", None),
    ("Запись вызова +375 (29) 123-45-67_261008_000014.m4a", None, "+375291234567"),
    ("Call recording 80291234567_261008_235914.mp3", None, "80291234567"),
])
def test_picker_projects_source_clock_and_label_without_sync_time(name, contact, phone):
    item = project_file(metadata(name), FOLDER)
    assert item.contact == contact and item.phone == phone
    assert item.call_occurred_at.date() == date(2026, 10, 8)
    assert item.call_occurred_at.utcoffset().total_seconds() == 10800
    assert matches_file(item, date_from=date(2026, 10, 8), date_to=date(2026, 10, 8), query="")
    assert not matches_file(item, date_from=date(2026, 10, 9), date_to=None, query="")


def test_picker_phone_search_normalizes_punctuation_and_name_search_case():
    phone = project_file(metadata("Вызов +375291234567_261008_000014.m4a"), FOLDER)
    assert matches_file(phone, date_from=None, date_to=None, query="+375 (29) 123-45")
    assert not matches_file(phone, date_from=None, date_to=None, query="123 клиент")
    contact = project_file(metadata("Вызов Дима Кондиционерщик_261008_170514.m4a"), FOLDER)
    assert matches_file(contact, date_from=None, date_to=None, query="КОНДИЦИОНЕР")


def test_picker_unknown_date_stays_unknown_and_foreign_non_audio_files_are_excluded():
    item = project_file(metadata("Вызов Клиент_неизвестное-время.m4a"), FOLDER)
    assert item.call_occurred_at is None
    assert not matches_file(item, date_from=date(2026, 10, 9), date_to=None, query="")
    assert matches_file(item, date_from=None, date_to=None, query="клиент")
    for changes in ({"parents": ["foreign-folder-0001"]}, {"trashed": True}, {"mimeType": "text/plain"}):
        assert project_file({**metadata("note.txt"), **changes}, FOLDER) is None
    assert project_file(metadata("Вызов Дима_261332_170514.m4a"), FOLDER).call_occurred_at is None


@pytest.mark.asyncio
async def test_picker_drive_page_read_is_folder_bound_and_has_no_media_or_dynamic_query():
    def handle(request):
        assert request.method == "GET" and request.url.path.endswith("/files")
        assert request.url.params["pageSize"] == "100"
        assert request.url.params["pageToken"] == "opaque-drive-token"
        assert "'chosen-folder-00000001' in parents" in request.url.params["q"]
        assert "alt" not in request.url.params
        return httpx.Response(200, json={"files": [metadata("Вызов Дима_261008_170514.m4a")], "nextPageToken": "next"})
    adapter = GoogleCallDriveAdapter("fake", client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    items, token = await adapter.list_recordings(FOLDER, page_token="opaque-drive-token", page_size=100)
    assert len(items) == 1 and token == "next"
