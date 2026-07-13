from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import db
from keyboards.kb import my_listings_item_kb, back_to_menu_kb
from config import CHANNEL_ID
from handlers.admin import delete_channel_listing

router = Router()


@router.message(Command("mening_elonlarim"))
@router.callback_query(F.data == "mylist:back")
async def my_listings(event, state: FSMContext = None):
    if isinstance(event, CallbackQuery):
        user_id = event.from_user.id
        answer = event.message.edit_text
    else:
        user_id = event.from_user.id
        answer = event.answer

    listings = await db.get_user_listings(user_id)
    if not listings:
        text = "📭 Sizda hozircha e'lonlar yo'q."
        kb = back_to_menu_kb()
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=kb)
        else:
            await event.answer(text, reply_markup=kb)
        return

    text = "📋 <b>Mening e'lonlarim:</b>\n\n"
    for i, l in enumerate(listings, 1):
        status_emoji = {"active": "🟢", "sold": "🔴", "expired": "⏰", "pending": "🕐", "deleted": "🗑"}.get(l["status"], "❓")
        text += f"{i}. {status_emoji} <b>{l['brand']} {l['model']}, {l['year']}</b> — ${l['price']:,}\n"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for l in listings:
        kb.button(
            text=f"{l['brand']} {l['model']} ({l['status']})",
            callback_data=f"mylist:view:{l['listing_id']}"
        )
    kb.button(text="🏠 Menyu", callback_data="main_menu")
    kb.adjust(1)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await event.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("mylist:view:"))
async def view_my_listing(call: CallbackQuery):
    listing_id = call.data.split(":", 2)[2]
    listing = await db.get_listing(listing_id)
    if not listing:
        await call.answer("E'lon topilmadi.", show_alert=True)
        return

    status_map = {"active": "🟢 Faol", "sold": "🔴 Sotilgan", "expired": "⏰ Muddati tugagan",
                  "pending": "🕐 Kutilmoqda", "deleted": "🗑 O'chirilgan"}
    desc_line = f"📝 {listing['description']}\n" if listing["description"] else ""
    text = (
        f"🚗 <b>{listing['brand']} {listing['model']}, {listing['year']}</b>\n"
        f"📍 {listing['city']}   🛣 {listing['mileage']:,} km\n"
        f"💰 ${listing['price']:,}\n"
        f"{desc_line}"
        f"📊 Holat: {status_map.get(listing['status'], listing['status'])}"
    )
    await call.message.edit_text(
        text,
        reply_markup=my_listings_item_kb(str(listing["listing_id"]), listing["status"]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("mylist:sold:"))
async def mark_sold(call: CallbackQuery, bot: Bot):
    listing_id = call.data.split(":", 2)[2]
    listing = await db.get_listing(listing_id)
    if listing and listing["user_id"] != call.from_user.id:
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await db.set_listing_status(listing_id, "sold")
    if listing:
        await delete_channel_listing(bot, listing)
    await call.answer("✅ E'lon 'Sotildi' deb belgilandi.", show_alert=True)
    await call.message.edit_text(
        "✅ E'lon sotildi deb belgilandi va qidiruv natijalaridan olib tashlandi.",
        reply_markup=back_to_menu_kb()
    )


@router.callback_query(F.data.startswith("mylist:extend:"))
async def extend_listing(call: CallbackQuery):
    listing_id = call.data.split(":", 2)[2]
    await db.extend_listing(listing_id)
    await call.answer("✅ E'lon 30 kunga uzaytirildi.", show_alert=True)
    await call.message.edit_text(
        "✅ E'loningiz 30 kunga uzaytirildi.",
        reply_markup=back_to_menu_kb()
    )


@router.callback_query(F.data.startswith("mylist:delete:"))
async def delete_listing(call: CallbackQuery, bot: Bot):
    listing_id = call.data.split(":", 2)[2]
    listing = await db.get_listing(listing_id)
    if listing and listing["user_id"] != call.from_user.id:
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    await db.set_listing_status(listing_id, "deleted")
    if listing:
        await delete_channel_listing(bot, listing)
    await call.answer("🗑 E'lon o'chirildi.", show_alert=True)
    await call.message.edit_text("🗑 E'lon o'chirildi.", reply_markup=back_to_menu_kb())


@router.callback_query(F.data.startswith("expire:"))
async def handle_expire(call: CallbackQuery):
    _, action, listing_id = call.data.split(":", 2)
    if action == "extend":
        await db.extend_listing(listing_id)
        await call.message.edit_text("✅ E'loningiz 30 kunga uzaytirildi.")
    else:
        await call.message.edit_text("E'lon muddati tugadi va o'chirildi.")
