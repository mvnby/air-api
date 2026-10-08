"""Date suggestions at the owning incoming boundary, without AI or a DB."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from schemas_incoming import IncomingCreatePayload
from services.incoming_command_service import IncomingCommandService


SOURCE = datetime(2026, 10, 7, 22, 30, tzinfo=ZoneInfo("Europe/Minsk"))


@pytest.mark.parametrize("text", [
    "ТО не завтра, дату уточнить",
    "ТО завтра или послезавтра в 09:00",
    "ТО завтра; созвониться сегодня в 18:00",
    "ТО через месяц, звонок завтра в 09:00",
])
def test_ambiguous_work_wish_is_not_a_date(text):
    _, fields = IncomingCommandService._fields(IncomingCreatePayload(request_text=text), SOURCE)
    assert fields["requested_at"] is None
    assert fields["date_precision"] is None
    assert "requested_at" not in fields["field_sources"]


@pytest.mark.parametrize("text", [
    "ТО не сегодня", "ТО завтра?", "ТО завтра или в пятницу",
    "ТО 08.10.2026 и 09.10.2026", "ТО завтра 09:00 и 10:00",
    "ТО завтра в 25:00", "ТО завтра в 09:75", "ТО на 31.02.2027",
    "ТО 31.02.2027, затем 10.03.2027", "ТО вчера",
    "ТО сегодня в 09:00", "ТО на 06.10.2026",
    "ТО завтра отменено", "Отменили заявку; ТО завтра",
    "Клиент хотел ТО завтра", "Если понадобится ТО завтра",
    "ТО уже выполнено; завтра", "ТО завтра, если получится",
    "Звонок завтра в 09:00", "ТО, Звонок, завтра в 09:00",
    "ТО завтра; позвонить в 18:00", "ТО завтра; В 18:00 позвонить",
    "ТО; позвонить завтра в 09:00", "ТО; через месяц; звонок завтра",
    "ТО завтра. Созвониться сегодня в 18:00", "ТО завтра\nсозвониться сегодня в 18:00",
    "ТО завтра; когда согласуем", "ТО завтра; отпадает", "ТО; завтра",
    "ТО завтра утром", "ТО завтра после звонка", "Клиент завтра",
    "ТО, Уточнение, завтра", "ТО, Билево, завтра",
    "ТО 2026-10-08T09:00:00+03:00", "ТО 08.10.2026 09:00 10:00",
])
def test_unsupported_or_nonpositive_wishes_remain_unknown(text):
    _, fields = IncomingCommandService._fields(IncomingCreatePayload(request_text=text), SOURCE)
    assert fields["requested_at"] is fields["date_precision"] is None
    assert "requested_at" not in fields["field_sources"]


@pytest.mark.parametrize("text,expected,precision", [
    ("ТО завтра в 09:00", "2026-10-08T09:00:00+03:00", "datetime"),
    ("ТО послезавтра", "2026-10-09T00:00:00+03:00", "date"),
    ("ТО сегодня", "2026-10-07T00:00:00+03:00", "date"),
    ("ТО сегодня в 23:00", "2026-10-07T23:00:00+03:00", "datetime"),
    ("Клиент хочет монтаж завтра", "2026-10-08T00:00:00+03:00", "date"),
    ("завтра в 9", "2026-10-08T09:00:00+03:00", "datetime"),
    ("ТО завтра к 9.30", "2026-10-08T09:30:00+03:00", "datetime"),
    ("ТО завтра 9 часов", "2026-10-08T09:00:00+03:00", "datetime"),
    ("ТО 08.10.2026 в 09:00", "2026-10-08T09:00:00+03:00", "datetime"),
    ("ТО на 08/10/26", "2026-10-08T00:00:00+03:00", "date"),
    ("ТО 08-10", "2026-10-08T00:00:00+03:00", "date"),
    ("ТО в пятницу", "2026-10-09T00:00:00+03:00", "date"),
    ("ТО квартиры +375291234567, район Билево, завтра 09:00; адрес уточнить; созвониться перед выездом", "2026-10-08T09:00:00+03:00", "datetime"),
])
def test_positive_work_wishes(text, expected, precision):
    _, fields = IncomingCommandService._fields(IncomingCreatePayload(request_text=text), SOURCE)
    assert fields["requested_at"] == expected
    assert fields["date_precision"] == precision
    assert fields["field_sources"]["requested_at"] == "text"


def test_missing_source_never_invents_an_anchor_and_manual_date_wins():
    _, fields = IncomingCommandService._fields(IncomingCreatePayload(request_text="ТО завтра"), None)
    assert fields["requested_at"] is None
    override = datetime(2027, 1, 1, 9, tzinfo=ZoneInfo("Asia/Tokyo"))
    _, fields = IncomingCommandService._fields(IncomingCreatePayload(request_text="ТО не завтра", requested_at=override), SOURCE)
    assert datetime.fromisoformat(fields["requested_at"]) == override
    assert fields["field_sources"]["requested_at"] == "provided"
    assert fields["date_precision"] == "datetime"


def test_long_malformed_contact_abstains():
    text = "1" * 11000 + "X ТО завтра"
    _, fields = IncomingCommandService._fields(IncomingCreatePayload(request_text=text), SOURCE)
    assert fields["requested_at"] is None


def test_only_provided_unlabelled_region_is_safe_date_context():
    payload = IncomingCreatePayload(request_text="ТО квартиры +375291234567, Билево, завтра 09:00; адрес уточнить", region_text="Билево")
    _, fields = IncomingCommandService._fields(payload, SOURCE)
    assert fields["requested_at"] == "2026-10-08T09:00:00+03:00"


@pytest.mark.parametrize("source,text", [
    (datetime(2026, 3, 7, 12, tzinfo=ZoneInfo("America/New_York")), "ТО завтра в 02:30"),
    (datetime(2026, 10, 31, 12, tzinfo=ZoneInfo("America/New_York")), "ТО завтра в 01:30"),
])
def test_invalid_or_multiple_local_timestamps_abstain(source, text):
    _, fields = IncomingCommandService._fields(IncomingCreatePayload(request_text=text), source)
    assert fields["requested_at"] is fields["date_precision"] is None
