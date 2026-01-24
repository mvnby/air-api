import logging
from aiogram import Bot
from core.config import settings

logger = logging.getLogger(__name__)

class BotService:
    @staticmethod
    async def send_message(user_id: int, text: str):
        """
        Sends a message to a specific Telegram user.
        Uses the shared BOT_TOKEN from settings.
        """
        try:
            bot = Bot(token=settings.BOT_TOKEN)
            async with bot.context():
                await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {user_id}: {e}")

    @staticmethod
    async def notify_installer_new_order(installer_tg_id: int, order_id: int, address: str, date_str: str, role: str):
        """
        Specific template for notifying an installer about a new job.
        """
        text = (
            f"<b>👷‍♂️ Назначен новый монтаж!</b>\n\n"
            f"🆔 <b>Заказ №{order_id}</b>\n"
            f"📍 Адрес: {address}\n"
            f"📅 Дата: {date_str}\n"
            f"🔧 Роль: {role}\n\n"
            f"<i>Пожалуйста, подтвердите получение!</i>"
        )
        await BotService.send_message(installer_tg_id, text)
