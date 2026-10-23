"""Bounded header data: never reuse untrusted raw RFC headers in outgoing mail."""

import re
from email.utils import getaddresses

MESSAGE_ID = re.compile(r"^<[^\s<>@,;\x00-\x1f\x7f]+@[^\s<>@,;\x00-\x1f\x7f]+>$")
ADDRESS = re.compile(r"^[^\s<>@,;\x00-\x1f\x7f]+@[^\s<>@,;\x00-\x1f\x7f]+\.[^\s<>@,;\x00-\x1f\x7f]+$")


def valid_message_id(value: str) -> bool:
    return len(value) <= 998 and MESSAGE_ID.fullmatch(value) is not None


def message_ids(value: str | None) -> list[str]:
    return list(dict.fromkeys(item for item in re.findall(r"<[^<>]+>", value or "")
                             if valid_message_id(item)))[-50:]


def reply_addresses(value: str | None) -> list[str]:
    return list(dict.fromkeys(address for _, address in getaddresses([value or ""])
                             if len(address) <= 254 and ADDRESS.fullmatch(address)))[:50]
