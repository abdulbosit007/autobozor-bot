from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from database.db import upsert_user
from keyboards.kb import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await upsert_user(message.from_user.id, message.from_user.username or "")
    await message.answer(
        "🚗 <b>AutoBozor'ga xush kelibsiz!</b>\n\n"
        "Bu yerda avtomobil sotishingiz yoki\n"
        "sotib olishingiz mumkin — bir necha soniyada.\n\n"
        "<b>Nima qilmoqchisiz?</b>",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "main_menu")
async def back_to_main(call: CallbackQuery):
    await call.message.edit_text(
        "🚗 <b>AutoBozor</b>\n\n<b>Nima qilmoqchisiz?</b>",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
