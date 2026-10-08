"""A small positive grammar for incoming work wishes, never scheduling.

Free prose outside this grammar stays text. Validate only the isolated date/time
with the existing parser; never let it search different actions for a timestamp.
"""

import re
from datetime import datetime, timezone

from services.bot_quick_order_service import BotQuickOrderService
from services.incoming_preview import NON_REQUEST
from services.incoming_agreements import explicit_instructions


_WEEKDAYS = "|".join(sorted(BotQuickOrderService.WEEKDAY_ALIASES, key=len, reverse=True))
_DATE = re.compile(
    rf"\b(?:сегодня|завтра|послезавтра|{_WEEKDAYS})\b"
    r"|(?<![\w./-])\d{1,2}[./-]\d{1,2}(?:[./-](?:\d{4}|\d{2}))?(?![\w/-]|[.]\d)",
    re.I,
)
_TIME = r"(?:(?:в|к)\s*)?\d{1,2}:\d{2}|(?:в|к)\s*\d{1,2}(?:[.]\d{2}|\s*час(?:а|ов)?|\s*ч)?|\d{1,2}\s*(?:час(?:а|ов)?|ч)"
# Accept a short present-tense request and service description. Unrecognized
# verbs (including cancellation, past and conditional wishes) cannot pass.
_PREFIX_WORD = (
    r"то|работы|работ|монтаж|установка|установку|обслуживание|ремонт|демонтаж|"
    r"квартиры|квартире|квартиру|квартир|дома|доме|дом|офиса|офисе|офис|"
    r"кондиционера|кондиционеров|кондиционер|оборудования|"
    r"клиент|клиента|хочет|хочу|нужно|нужен|нужна|требуется|"
    r"сделать|провести|выполнить|на|в|к"
)
_PREFIX = re.compile(rf"(?:(?:{_PREFIX_WORD})\b[\s,]*)*")
# These qualifiers make even an otherwise recognizable fragment uncertain.
_UNCERTAIN = re.compile(
    r"\b(?:не|нет|или|либо|если|возможно|может|наверное|через|вчера|раньше|"
    r"отмен\w*|отказ\w*|хотел\w*|передум\w*|перенос\w*|перенес\w*|перенёс\w*)\b|[?]"
)


def requested_date(
    text: str, source_time: datetime | None, *, region_text: str | None = None,
) -> tuple[datetime | None, str | None]:
    """Return one unambiguous date and its precision, or safely abstain.

    Both date and optional time must finish the same clause. Other dated clauses
    or times, unsupported actions, uncertainty and past timestamps abstain.
    """
    if source_time is None:
        return None, None
    value = text.strip()
    if _UNCERTAIN.search(value.casefold()) or NON_REQUEST.search(value):
        return None, None
    # A dotted time explicitly introduced by в/к is not a second date.
    dotted_times = list(re.finditer(r"\b(?:в|к)\s*\d{1,2}[.]\d{2}\b", value, re.I))
    dates = [match for match in _DATE.finditer(value)
             if not any(time.start() <= match.start() and match.end() <= time.end() for time in dotted_times)]
    if len(dates) != 1:
        return None, None
    date = dates[0]
    # Keep numeric dots in dates and times; split only sentence punctuation.
    separators = list(re.finditer(r"[;\n!]|(?<!\d)[.]|[.](?!\d)", value))
    left = max([0] + [separator.end() for separator in separators if separator.end() <= date.start()])
    right = min([len(value)] + [separator.start() for separator in separators if separator.start() >= date.end()])
    candidate = value[left:right]
    prefix = value[left:date.start()].strip()
    # A dated call is never a work wish, even in a district-shaped field.
    if re.search(r"\b(?:звон\w*|позвон\w*|созвон\w*|перезвон\w*)\b", candidate, re.I):
        return None, None
    # Only a labelled district or an explicitly provided region is context;
    # guessing any capitalized noun would swallow actions such as Уточнение.
    prefix = re.sub(r",\s*район\s+[А-ЯЁа-яёіўІЎ-]+\s*,?\s*$", ", ", prefix)
    if region_text:
        prefix = re.sub(rf",\s*{re.escape(region_text)}\s*,?\s*$", ", ", prefix, flags=re.I)
    # Bound contact length before matching words; repeated unbounded digit
    # groups would backtrack catastrophically on a long malformed source.
    prefix = re.sub(r"(?<!\w)\+?\d[\d ()-]{6,30}(?!\w)", " ", prefix)
    if not _PREFIX.fullmatch(prefix.casefold()):
        return None, None
    if not re.search(r"\b(?:то|работы|работ|монтаж|установк\w*|обслуживание|ремонт|демонтаж)\b", prefix, re.I):
        if not re.fullmatch(r"(?:(?:на|в|к|хочу)\s*)*", prefix.casefold()):
            return None, None
    tail = value[date.end():right].strip(" ,")
    if tail and not re.fullmatch(_TIME, tail):
        return None, None
    # No timestamp from an independent clause may supply time or be silently
    # ignored as part of a different action.
    other_clauses = value[:left] + ";" + value[right:]
    if re.search(rf"\b(?:{_TIME})\b", other_clauses, re.I):
        return None, None
    # Outside the work clause accept only the existing standalone positive
    # address/prior-call instructions. Unknown prose may qualify or cancel the
    # wish; it must not be silently discarded to manufacture certainty.
    for clause in re.split(r"[;\n!]|(?<!\d)[.]|[.](?!\d)", other_clauses):
        if clause.strip() and not any(explicit_instructions(clause)):
            return None, None
    parsed = BotQuickOrderService._parse_date(date.group() + (" " + tail if tail else ""), now=source_time)
    if parsed is None or (parsed < source_time if tail else parsed.date() < source_time.date()):
        return None, None
    if tail and (
        parsed.astimezone(timezone.utc).astimezone(parsed.tzinfo) != parsed
        or parsed.replace(fold=0).utcoffset() != parsed.replace(fold=1).utcoffset()
    ):
        # A nonexistent or ambiguous local time is not a single timestamp.
        return None, None
    return parsed, "datetime" if tail else "date"
