import asyncio
from .config import bot, dp
from .handlers import base, catalog, orders, admin

async def main():
    # Register routers in specific order
    dp.include_router(base.router)
    dp.include_router(admin.router) # Admin before catalog to catch specific admin actions if any overlap
    dp.include_router(orders.router)
    dp.include_router(catalog.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
