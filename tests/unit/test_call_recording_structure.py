from datetime import datetime
from zoneinfo import ZoneInfo

from services.call_recording_structure import ExtractedCall, action_proposals, samsung_call_time


def proposals(transcript, actions, source=None):
    return action_proposals(ExtractedCall(summary="Разбор", actions=actions), transcript=transcript, call_occurred_at=source, manual_phone=None)


def test_samsung_filename_is_original_minsk_time_not_contact_identity():
    assert samsung_call_time("Вызов Человек_261008_185601.m4a").isoformat() == "2026-10-08T18:56:01+03:00"
    assert samsung_call_time("Вызов Иван_260231_991001.m4a") is None
    assert samsung_call_time("семейный разговор.m4a") is None


def test_phone_requires_contiguous_grounded_phone_span():
    transcript = "Цена 375 рублей. Заказ 29123. Код 4567. Нужно обслуживание."
    result = proposals(transcript, [{"kind": "incoming", "text": "Нужно обслуживание", "evidence": "Нужно обслуживание", "phone": "+375291234567"}])
    assert result[0]["payload"]["phone"] is None
    transcript = "Телефон +375 (29) 123-45-67. Нужно обслуживание."
    result = proposals(transcript, [{"kind": "incoming", "text": "Нужно обслуживание", "evidence": "Нужно обслуживание", "phone": "+375291234567"}])
    assert result[0]["payload"]["phone"] == "+375291234567"


def test_ungrounded_evidence_or_relative_phrase_never_manufactures_date():
    source = datetime(2026, 10, 8, 18, tzinfo=ZoneInfo("Europe/Minsk"))
    result = proposals("Обслуживание. Дослать фото свидетельства.", [
        {"kind": "incoming", "text": "Нужно обслуживание завтра", "evidence": "Обслуживание", "requested_time_text": "завтра утром"},
        {"kind": "task", "text": "Дослать фото", "evidence": "Дослать фото свидетельства", "requested_time_text": "завтра в 9:00"},
        {"kind": "task", "text": "Не из разговора", "evidence": "Вымышленная цитата"},
    ], source)
    assert len(result) == 2
    assert result[0]["payload"]["requested_at"] is None
    assert result[0]["payload"]["requested_time_text"] is None
    assert result[1]["payload"]["due_at"] is None


def test_late_call_tomorrow_uses_original_time_and_date_only_task_has_no_midnight_deadline():
    source = datetime(2026, 10, 8, 18, tzinfo=ZoneInfo("Europe/Minsk"))
    transcript = "Нужно обслуживание завтра утром. Дослать фото завтра."
    result = proposals(transcript, [
        {"kind": "incoming", "text": "Нужно обслуживание", "evidence": "Нужно обслуживание завтра утром", "requested_time_text": "завтра утром", "service_type": "maintenance", "clarification_requested": True},
        {"kind": "task", "text": "Дослать фото", "evidence": "Дослать фото завтра", "requested_time_text": "завтра"},
    ], source)
    assert result[0]["payload"]["requested_at"] is None
    assert result[0]["payload"]["requested_time_text"] == "завтра утром"
    assert result[0]["payload"]["clarification_requested"] is True
    assert result[1]["payload"]["due_at"] is None
    assert "Указан только день, время требует уточнения" in result[1]["needs_clarification"]


def test_unknown_clock_keeps_relative_phrase_without_processing_clock():
    result = proposals("Завтра в 9:00", [{"kind": "callback", "text": "Перезвонить", "evidence": "Завтра в 9:00", "requested_time_text": "Завтра в 9:00"}])
    assert result[0]["payload"]["due_at"] is None
    assert "Дата требует уточнения" in result[0]["needs_clarification"]
