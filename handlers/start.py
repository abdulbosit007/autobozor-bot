from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from config import FREE_LISTING_LIMIT
from database import db
from keyboards.kb import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.upsert_user(message.from_user.id, message.from_user.username or "")
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


@router.message(Command("sell"))
async def cmd_sell(message: Message, state: FSMContext):
    # Simulate pressing the Sell button
    await db.upsert_user(message.from_user.id, message.from_user.username or "")
    count = await db.count_active_listings(message.from_user.id)
    user = await db.get_user(message.from_user.id)
    paid_slots = user.get("paid_slots", 0) or 0

    if count >= FREE_LISTING_LIMIT and paid_slots == 0:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 To'lov so'rovi yuborish", callback_data="sell:pay_request")
        kb.button(text="🏠 Menyu", callback_data="main_menu")
        kb.adjust(1)
        await message.answer(
            f"⚠️ Bepul limit: <b>{FREE_LISTING_LIMIT} ta</b>\n"
            f"Faol e'lonlaringiz: <b>{count} ta</b>\n\n"
            "Qo'shimcha e'lon uchun to'lov so'rovi yuboring.",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from keyboards.kb import brands_kb
    from handlers.sell import SellStates
    if count >= FREE_LISTING_LIMIT:
        await state.update_data(is_paid=True)
    else:
        await state.update_data(is_paid=False)
    await state.set_state(SellStates.brand)
    await message.answer(
        "🚗 <b>Avtomobil rusumini tanlang:</b>",
        reply_markup=brands_kb("sell"), parse_mode="HTML"
    )


@router.message(Command("buy"))
async def cmd_buy(message: Message, state: FSMContext):
    await db.upsert_user(message.from_user.id, message.from_user.username or "")
    from handlers.buy import BuyStates
    from keyboards.kb import brands_kb
    await state.clear()
    await state.set_state(BuyStates.brand)
    await message.answer(
        "🔍 <b>Qaysi rusum avtomobilni qidiryapsiz?</b>",
        reply_markup=brands_kb("buy"), parse_mode="HTML"
    )


@router.message(Command("mylistings"))
async def cmd_mylistings(message: Message):
    from handlers.listings import my_listings
    await my_listings(message)


@router.message(Command("clear"))
async def cmd_clear(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🧹 <b>Tozalandi.</b>\n\nNima qilmoqchisiz?",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )


@router.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await db.upsert_user(user_id, message.from_user.username or "")
        user = await db.get_user(user_id)

    count = await db.count_active_listings(user_id)
    paid_slots = user.get("paid_slots", 0) or 0
    free_left = max(0, FREE_LISTING_LIMIT - count)
    is_dealer = user.get("is_dealer", False)

    if is_dealer:
        status_line = "👑 <b>Dealer hisobi</b> — cheksiz e'lonlar"
    elif free_left > 0:
        status_line = f"🆓 Bepul e'lonlar: <b>{free_left} ta qoldi</b> ({count}/{FREE_LISTING_LIMIT})"
    else:
        status_line = f"🔴 Bepul limit tugagan ({count}/{FREE_LISTING_LIMIT})"

    await message.answer(
        f"📊 <b>Sizning holatiniz:</b>\n\n"
        f"{status_line}\n"
        f"💳 To'langan slotlar: <b>{paid_slots} ta</b>\n"
        f"📋 Faol e'lonlar: <b>{count} ta</b>",
        parse_mode="HTML"
    )
