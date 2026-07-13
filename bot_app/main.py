import asyncio
from aiogram import types
from aiogram.types import BotCommand
from .config import bot, dp
from .handlers import admin, base, catalog, repair_context, work
from core.config import settings
from core.database import async_session_maker
from core.logger import setup_logging
from core.startup_checks import run_production_startup_checks
from services.runtime_lock_service import RuntimeLockService

# Setup logging with session-specific bot.log (cleared on restart)
logger = setup_logging(session_log_file="logs/bot.log", clear_session_log=True)

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
    logger.exception(f"Bot error: {event.exception} for event {event.update}")
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

    await run_production_startup_checks(settings)

    if wait_when_disabled:
        runtime_lock = await RuntimeLockService.wait_until_acquired(
            async_session_maker,
            "mvn:telegram_bot",
        )
    else:
        runtime_lock = await RuntimeLockService.try_acquire(
            async_session_maker,
            "mvn:telegram_bot",
        )
    if not runtime_lock.acquired:
        logger.warning("Telegram bot polling disabled: %s.", runtime_lock.reason)
        return

    logger.info("Starting bot polling: %s.", decision.reason)
    # Register routers in specific order
    dp.include_router(base.router)
    dp.include_router(work.router)
    dp.include_router(catalog.router)
    dp.include_router(repair_context.router)
    dp.include_router(admin.router)
    
    try:
        await _setup_bot_commands()
        await bot.delete_webhook(drop_pending_updates=settings.BOT_DROP_PENDING_UPDATES)
        await dp.start_polling(bot)
    finally:
        await runtime_lock.release()

if __name__ == "__main__":
    asyncio.run(main())
