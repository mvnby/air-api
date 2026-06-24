from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation
from core.config import settings
from .fsm_storage import SqlAlchemyFsmStorage


def _resolve_bot_token() -> str:
    token = str(settings.BOT_TOKEN or "").strip()
    if token:
        return token
    if not settings.bot_control_decision.enabled:
        return "0:disabled-bot-token"
    raise RuntimeError("BOT_TOKEN is required when Telegram bot polling is enabled")


bot = Bot(token=_resolve_bot_token())
dp = Dispatcher(storage=SqlAlchemyFsmStorage(), events_isolation=SimpleEventIsolation())
