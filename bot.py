import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from database.db import init_db, expire_old_listings
from handlers import start, sell, buy, listings, admin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)


async def notify_expired(bot: Bot):
    expired = await expire_old_listings()
    for row in expired:
        try:
            await bot.send_message(
                row["user_id"],
                f"⏰ <b>E'loningiz muddati tugadi.</b>\n"
                f"🚗 {row['brand']} {row['model']}\n\n"
                f"Faolligini uzaytirasizmi?",
                reply_markup=__import__("keyboards.kb", fromlist=["extend_kb"]).extend_kb(row["listing_id"]),
                parse_mode="HTML"
            )
        except Exception:
            pass


async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(sell.router)
    dp.include_router(buy.router)
    dp.include_router(listings.router)
    dp.include_router(admin.router)

    await init_db()
    log.info("Database initialized")

    await bot.set_my_commands([
        BotCommand(command="start",     description="🏠 Bosh sahifa"),
        BotCommand(command="sell",      description="🔴 Avtomobil sotish"),
        BotCommand(command="buy",       description="🟢 Avtomobil sotib olish"),
        BotCommand(command="mylistings",description="📋 Mening e'lonlarim"),
        BotCommand(command="status",    description="📊 E'lon limitim holati"),
    ])

    scheduler = AsyncIOScheduler()
    scheduler.add_job(notify_expired, "cron", hour=10, minute=0, args=[bot])
    scheduler.start()
    log.info("Scheduler started")

    log.info("Bot starting...")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
