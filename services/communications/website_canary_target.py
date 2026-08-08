from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from services.communications.tenant_website_events import (
    TENANT_WEBSITE_EVENT_TEMPLATE_KEYS,
)


CANARY_KIND_OPERATIONS = "operations"
CANARY_KIND_WEBSITE = "website"
_EVENT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_RECIPIENT_KEY_PATTERN = re.compile(r"^staff:[1-9][0-9]*$")


class WebsiteCanaryScopeMismatch(ValueError):
    pass


@dataclass(frozen=True)
class WebsiteCanaryTarget:
    """Immutable tenant website target carried by one runtime revision."""

    event_id: str
    event_type: str
    tenant_id: int
    storefront_id: int
    recipient_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not _EVENT_ID_PATTERN.fullmatch(
            self.event_id
        ):
            raise ValueError("Website canary event ID is invalid")
        if self.event_type not in TENANT_WEBSITE_EVENT_TEMPLATE_KEYS:
            raise ValueError("Website canary event type is not allowlisted")
        for field_name in ("tenant_id", "storefront_id"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"Website canary {field_name} is invalid")
        if (
            not isinstance(self.recipient_key, str)
            or not _RECIPIENT_KEY_PATTERN.fullmatch(self.recipient_key)
        ):
            raise ValueError("Website canary recipient key is invalid")

    @property
    def template_key(self) -> str:
        return TENANT_WEBSITE_EVENT_TEMPLATE_KEYS[self.event_type]

    def assert_event_plan(
        self,
        *,
        event_id: str,
        event_type: str,
        template_key: str,
        audience: str,
        render_context: Mapping[str, object],
    ) -> None:
        try:
            tenant_id = int(render_context["tenant_id"])
            storefront_id = int(render_context["storefront_id"])
        except (KeyError, TypeError, ValueError):
            raise WebsiteCanaryScopeMismatch(
                "Website canary event scope is invalid"
            ) from None
        if (
            event_id != self.event_id
            or event_type != self.event_type
            or template_key != self.template_key
            or audience != "tenant_website_management"
            or tenant_id != self.tenant_id
            or storefront_id != self.storefront_id
        ):
            raise WebsiteCanaryScopeMismatch(
                "Website canary event scope is inconsistent"
            )
