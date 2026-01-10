from aiogram import Bot, Dispatcher
from database import async_session_maker
from core.config import settings
from core.logger import logger

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
