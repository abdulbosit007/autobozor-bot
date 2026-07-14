from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID, CHANNEL_ID
from database import db
from keyboards.kb import back_to_menu_kb, admin_listing_kb

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def delete_channel_listing(bot: Bot, listing: dict):
    """Delete all channel messages for a listing (handles media groups)."""
    ids = listing.get("channel_msg_ids") or []
    if not ids and listing.get("channel_msg_id"):
        ids = [listing["channel_msg_id"]]
    for mid in ids:
        try:
            await bot.delete_message(CHANNEL_ID, mid)
        except Exception:
            pass


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    pending = await db.get_pending_listings()
    text = (
        f"👑 <b>Admin panel</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{stats['users']}</b>\n"
        f"🟢 Faol e'lonlar: <b>{stats['active']}</b>\n"
        f"🔴 Sotilgan: <b>{stats['sold']}</b>\n"
        f"🕐 Kutilmoqda: <b>{stats['pending']}</b>\n\n"
        f"/pending — kutilayotgan e'lonlar\n"
        f"/stats — statistika"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("pending"))
async def admin_pending(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    listings = await db.get_pending_listings()
    if not listings:
        await message.answer("✅ Kutilayotgan e'lonlar yo'q.")
        return
    await message.answer(f"🕐 {len(listings)} ta e'lon kutilmoqda:")
    for listing in listings[:5]:  # show 5 at a time
        desc_line = f"📝 {listing['description']}\n" if listing["description"] else ""
        text = (
            f"🆕 <b>{listing['brand']} {listing['model']}, {listing['year']}</b>\n"
            f"📍 {listing['city']}   🛣 {listing['mileage']:,} km\n"
            f"💰 ${listing['price']:,}\n"
            f"{desc_line}"
            f"🆔 <code>{listing['listing_id']}</code>"
        )
        try:
            photos = listing["photo_file_ids"]
            if photos:
                await bot.send_photo(
                    message.chat.id, photos[0], caption=text,
                    reply_markup=admin_listing_kb(str(listing["listing_id"])),
                    parse_mode="HTML"
                )
            else:
                await message.answer(text, reply_markup=admin_listing_kb(str(listing["listing_id"])), parse_mode="HTML")
        except Exception as e:
            await message.answer(f"Error showing listing: {e}")


# ── Approve / Reject ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:approve:"))
async def approve_listing(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    listing_id = call.data.split(":", 2)[2]
    listing = await db.get_listing(listing_id)
    if not listing:
        await call.answer("E'lon topilmadi.", show_alert=True)
        return

    if listing["status"] != "pending":
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer(
            f"⚠️ Bu e'lon allaqachon bekor qilingan (sotuvchi tomonidan). Tasdiqlash mumkin emas.",
            show_alert=True
        )
        return

    await db.approve_listing(listing_id)

    # Post to channel
    desc_line = f"📝 {listing['description']}\n" if listing["description"] else ""
    phone = listing.get("phone") or ""
    caption = (
        f"🚗 <b>{listing['brand']} {listing['model']}, {listing['year']}</b>\n"
        f"📍 {listing['city']}\n"
        f"🛣 {listing['mileage']:,} km\n"
        f"💰 <b>${listing['price']:,}</b>\n"
        f"📱 <b>{phone}</b>\n"
        f"{desc_line}"
    )

    tg_user_id = listing.get("tg_user_id")
    contact_kb = None
    if tg_user_id:
        from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
        btn = IKB()
        btn.button(text="💬 Telegram orqali bog'lanish", url=f"tg://user?id={tg_user_id}")
        contact_kb = btn.as_markup()

    photos = listing["photo_file_ids"]
    try:
        if len(photos) == 1:
            msg = await bot.send_photo(
                CHANNEL_ID, photos[0], caption=caption,
                reply_markup=contact_kb, parse_mode="HTML"
            )
            await db.set_channel_msg(listing_id, msg.message_id, [msg.message_id])
        else:
            media = [InputMediaPhoto(media=pid) for pid in photos]
            media[0] = InputMediaPhoto(media=photos[0], caption=caption, parse_mode="HTML")
            msgs = await bot.send_media_group(CHANNEL_ID, media)
            all_ids = [m.message_id for m in msgs]
            await db.set_channel_msg(listing_id, all_ids[0], all_ids)
            # send contact button as separate message after media group
            if contact_kb:
                btn_msg = await bot.send_message(
                    CHANNEL_ID, "📲",
                    reply_markup=contact_kb
                )
                all_ids.append(btn_msg.message_id)
                await db.set_channel_msg(listing_id, all_ids[0], all_ids)
    except Exception as e:
        await call.message.answer(f"⚠️ Kanalga joylashda xato: {e}")

    # Notify seller with Sotildi control button
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    sold_kb = InlineKeyboardBuilder()
    sold_kb.button(text="✅ Sotildi", callback_data=f"mylist:sold:{listing_id}")
    sold_kb.button(text="🗑 O'chirish", callback_data=f"mylist:delete:{listing_id}")
    sold_kb.adjust(2)
    try:
        await bot.send_message(
            listing["user_id"],
            f"✅ <b>E'loningiz tasdiqlandi va kanalda joylashtirildi!</b>\n\n"
            f"🚗 {listing['brand']} {listing['model']}, {listing['year']}\n"
            f"💰 ${listing['price']:,}\n\n"
            f"Mashina sotilganda pastdagi tugmani bosing 👇",
            reply_markup=sold_kb.as_markup(),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("✅ E'lon tasdiqlandi va kanalga joylashtirildi.", show_alert=True)


@router.callback_query(F.data.startswith("admin:reject:"))
async def reject_listing(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id):
        await call.answer("Ruxsat yo'q.", show_alert=True)
        return
    listing_id = call.data.split(":", 2)[2]
    listing = await db.get_listing(listing_id)
    if not listing:
        await call.answer("E'lon topilmadi.", show_alert=True)
        return

    await db.set_listing_status(listing_id, "rejected")  # frees the slot

    await delete_channel_listing(bot, listing)

    try:
        await bot.send_message(
            listing["user_id"],
            "❌ <b>E'loningiz qabul qilinmadi.</b>\n"
            "Qoidalarga zid yoki ma'lumotlar to'liq emas.\n\n"
            "Qayta urinib ko'ring.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await call.message.edit_reply_markup(reply_markup=None)
    await call.answer("❌ E'lon rad etildi.", show_alert=True)


@router.message(Command("stats"))
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    stats = await db.get_stats()
    await message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['users']}</b>\n"
        f"🟢 Faol e'lonlar: <b>{stats['active']}</b>\n"
        f"🔴 Sotilgan: <b>{stats['sold']}</b>\n"
        f"🕐 Kutilmoqda: <b>{stats['pending']}</b>",
        parse_mode="HTML"
    )
