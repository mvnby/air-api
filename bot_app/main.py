import asyncio
import logging
from aiogram import types
from aiogram.types import BotCommand
from .access import BotAccessUnavailableError
from .access_runtime import close_bot_access_provider, verify_bot_access_startup
from .api_gateway import BotApiAuthorizationError, BotApiError
from .api_runtime import close_bot_api_gateway
from .config import bot, dp
from .handlers import admin, base, catalog, repair_context, work
from .runtime_lease import BotRuntimeLease
from .settings import settings

# Setup logging with session-specific bot.log (cleared on restart)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

STAFF_BOT_COMMANDS = [
    BotCommand(command="start", description="Открыть рабочее меню"),
    BotCommand(command="menu", description="Показать рабочее меню"),
    BotCommand(command="help", description="Показать рабочее меню и подсказки"),
    BotCommand(command="quick_order", description="Быстрый заказ из текста звонка"),
    BotCommand(command="selection", description="Подбор кондиционеров: 7х2, 7, 12"),
    BotCommand(command="search", description="Поиск товара: Midea 12"),
    BotCommand(command="tasks", description="Мои задачи и отчеты"),
]

# Global Error Handler for Bot
@dp.error()
async def error_handler(event: types.ErrorEvent):
    if isinstance(event.exception, BotAccessUnavailableError):
        logger.error("Bot staff access unavailable: %s", event.exception)
        callback = event.update.callback_query
        if callback is not None:
            await callback.answer("Сервис авторизации временно недоступен. Попробуйте позже.", show_alert=True)
        elif event.update.message is not None:
            await event.update.message.answer("Сервис авторизации временно недоступен. Попробуйте позже.")
        return True
    if isinstance(event.exception, BotApiAuthorizationError):
        logger.warning("Bot staff action denied: %s", event.exception)
        callback = event.update.callback_query
        if callback is not None:
            await callback.answer("Недостаточно прав для этого действия.", show_alert=True)
        elif event.update.message is not None:
            await event.update.message.answer("Недостаточно прав для этого действия.")
        return True
    if isinstance(event.exception, BotApiError):
        logger.error("Bot backend API unavailable: %s", event.exception)
        callback = event.update.callback_query
        if callback is not None:
            await callback.answer("Рабочий сервис временно недоступен. Попробуйте позже.", show_alert=True)
        elif event.update.message is not None:
            await event.update.message.answer("Рабочий сервис временно недоступен. Попробуйте позже.")
        return True
    logger.error(
        "Bot error: %s for event %s",
        event.exception,
        event.update,
        exc_info=(type(event.exception), event.exception, event.exception.__traceback__),
    )
    return True

async def _idle_when_disabled() -> None:
    while True:
        await asyncio.sleep(3600)


async def _setup_bot_commands() -> None:
    await bot.set_my_commands(STAFF_BOT_COMMANDS)


async def main(*, wait_when_disabled: bool = True):
    decision = settings.bot_control_decision
    if not decision.enabled:
        logger.warning("Telegram bot polling disabled: %s.", decision.reason)
        if wait_when_disabled:
            logger.info("Bot process is idling without polling to avoid restart loops.")
            await _idle_when_disabled()
        return

    runtime_lease = BotRuntimeLease()
    try:
        await verify_bot_access_startup()
        if wait_when_disabled:
            await runtime_lease.wait_until_acquired()
        elif not await runtime_lease.try_acquire():
            logger.warning("Telegram bot polling disabled: %s.", runtime_lease.reason)
            return

        logger.info("Starting bot polling: %s.", decision.reason)
        dp.include_router(base.router)
        dp.include_router(work.router)
        dp.include_router(catalog.router)
        dp.include_router(repair_context.router)
        dp.include_router(admin.router)
        await _setup_bot_commands()
        await bot.delete_webhook(drop_pending_updates=settings.BOT_DROP_PENDING_UPDATES)
        polling_task = asyncio.create_task(dp.start_polling(bot))
        lease_lost_task = asyncio.create_task(runtime_lease.lost_event.wait())
        done, pending = await asyncio.wait(
            {polling_task, lease_lost_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if lease_lost_task in done and runtime_lease.lost_event.is_set():
            await dp.stop_polling()
            raise RuntimeError("Telegram runtime lease was lost; polling stopped")
        await polling_task
    finally:
        await close_bot_access_provider()
        await runtime_lease.release()
        await close_bot_api_gateway()

if __name__ == "__main__":
    asyncio.run(main())
