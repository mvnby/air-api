import os
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from database import async_session_maker

load_dotenv()
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

if not API_TOKEN:
    raise ValueError("BOT_TOKEN is not set in .env")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
