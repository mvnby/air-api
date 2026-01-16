import asyncio
from aiogram import types
from .config import bot, dp
from .handlers import base, catalog, orders, admin, favorites, cart
from core.logger import setup_logging

# Setup logging with session-specific bot.log (cleared on restart)
logger = setup_logging(session_log_file="logs/bot.log", clear_session_log=True)

# Global Error Handler for Bot
@dp.error()
async def error_handler(event: types.ErrorEvent):
    logger.exception(f"Bot error: {event.exception} for event {event.update}")
    return True 

async def main():
    logger.info("Starting bot...")
    # Register routers in specific order
    dp.include_router(base.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(orders.router)
    dp.include_router(favorites.router)
    dp.include_router(admin.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
