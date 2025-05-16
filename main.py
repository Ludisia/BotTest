import os
import asyncio
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from handlers import common, laundry, restroom, admin
from database import init_db

# Инициализация
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Инициализация бота
bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher(storage=MemoryStorage())

# Включение роутеров
dp.include_router(common.router)
dp.include_router(admin.router)
dp.include_router(laundry.router)
dp.include_router(restroom.router)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация БД
init_db()

async def on_startup(dispatcher: Dispatcher):
    asyncio.create_task(check_and_send_notifications())
    logger.info("Бот запущен")

async def on_shutdown(dispatcher: Dispatcher):
    await bot.session.close()
    logger.info("Бот остановлен")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, on_startup=on_startup, on_shutdown=on_shutdown)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")