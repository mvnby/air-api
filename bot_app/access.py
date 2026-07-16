"""Bot-owned access context and provider boundary."""

from dataclasses import dataclass, field
from typing import Protocol


class BotAccessUnavailableError(RuntimeError):
    """Staff authorization cannot be checked safely at the moment."""


@dataclass(frozen=True)
class BotAccessContext:
    telegram_id: int
    is_staff: bool = False
    display_name: str = ""
    primary_role: str = ""
    roles: list[str] = field(default_factory=list)
    legacy_installer_id: int | None = None
    is_manager: bool = False
    is_executor: bool = False


class BotAccessProvider(Protocol):
    async def health(self) -> None: ...

    async def get_context(self, telegram_id: int | str | None) -> BotAccessContext: ...

    async def aclose(self) -> None: ...
