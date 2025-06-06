from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from colorama import Fore as f, init as finit
import asyncio
import logging

from config import settings
from app.handlers import router as MainRouter

async def main():
	finit(autoreset=True)
	bot = Bot(token=settings.BOT_TOKEN)
	dp = Dispatcher(storage=MemoryStorage())
	dp.include_router(MainRouter)
	await dp.start_polling(bot)


if __name__ == "__main__":
	try:
		logging.basicConfig(level=logging.INFO, datefmt=settings.LOGGING_DATEFMT)
		asyncio.run(main())
	except KeyboardInterrupt:
		print(f"{f.RED} Detected Ctrl + C ... Bot stoped")

#! В КАЖДОМ HANDLER ИДУТ ЗАПРОСЫ В БД, ЧТО МОЖНО ИЗБЕЖАТЬ, ИСПОЛЬЗУЯ FSMCONTEXT, НО КАК ТО ВПАДЛУ ПЕРЕПИСЫВАТЬ)

#? МБ ДОДЕЛАТЬ СИСТЕМУ РЕЙТИНГА И ЗАГРУЖЕННОСТИ, А ТАКЖЕ ПОДТВЕРЖДЕНИЕ ПОЛУЧЕНИЯ ЗАДАЧИ