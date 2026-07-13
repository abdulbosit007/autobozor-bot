import datetime
from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup,
                            KeyboardButton, ReplyKeyboardRemove)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import FREE_LISTING_LIMIT, MIN_PHOTOS, MAX_PHOTOS, ADMIN_ID
from database import db
from keyboards.kb import (
    brands_kb, models_kb, years_kb, cities_kb,
    confirm_listing_kb, back_to_menu_kb, admin_listing_kb
)

router = Router()

CURRENT_YEAR = datetime.datetime.now().year
MIN_YEAR = 1970
MAX_MILEAGE = 999_999
MAX_PRICE = 9_999_999
MIN_PRICE = 100


class SellStates(StatesGroup):
    brand       = State()
    model       = State()
    year        = State()
    mileage     = State()
    price       = State()
    city        = State()
    phone       = State()
    photos      = State()
    description = State()
    confirm     = State()


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamimni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


def photos_done_inline():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tayyor", callback_data="sell:photos_done")
    return kb.as_markup()


# ── Entry ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sell")
async def sell_start(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    count = await db.count_active_listings(user_id)
    user = await db.get_user(user_id)

    if count >= FREE_LISTING_LIMIT:
        paid_slots = user.get("paid_slots", 0) or 0
        if paid_slots > 0:
            # Has a paid slot approved — let them post
            await state.update_data(is_paid=True)
        else:
            # No paid slot — show payment request option
            kb = InlineKeyboardBuilder()
            kb.button(text="💳 To'lov so'rovi yuborish", callback_data="sell:pay_request")
            kb.button(text="🏠 Menyu", callback_data="main_menu")
            kb.adjust(1)
            await call.message.edit_text(
                f"⚠️ Sizda allaqachon <b>{count} ta</b> faol e'lon bor.\n\n"
                f"Bepul limit: <b>{FREE_LISTING_LIMIT} ta</b>\n\n"
                "Qo'shimcha e'lon joylashtirish uchun <b>har bir e'lon uchun to'lov</b> talab qilinadi.\n"
                "To'lov so'rovi yuboring — admin to'lovni tasdiqlaydi va siz e'lon joylashtirishingiz mumkin.",
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
            return
    else:
        await state.update_data(is_paid=False)

    await state.set_state(SellStates.brand)
    await call.message.edit_text(
        "🚗 <b>Avtomobil rusumini tanlang:</b>",
        reply_markup=brands_kb("sell"),
        parse_mode="HTML"
    )


# ── Payment request ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sell:pay_request")
async def send_pay_request(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    user_phone = user.get("phone") or "Noma'lum"
    username = call.from_user.username or str(call.from_user.id)

    req_id = await db.create_payment_request(call.from_user.id, username, user_phone)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ To'lov tasdiqlandi", callback_data=f"pay:approve:{req_id}")
    kb.button(text="❌ Rad etish",          callback_data=f"pay:reject:{req_id}")
    kb.adjust(2)

    await call.bot.send_message(
        ADMIN_ID,
        f"💳 <b>Yangi to'lov so'rovi</b>\n\n"
        f"👤 @{username}\n"
        f"📱 {user_phone}\n"
        f"🆔 User ID: <code>{call.from_user.id}</code>\n\n"
        f"To'lovni qabul qiling va tasdiqlang.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await call.message.edit_text(
        "✅ <b>So'rovingiz adminga yuborildi.</b>\n\n"
        "Admin to'lovni tasdiqlashi bilan sizga xabar keladi.\n"
        "To'lovni amalga oshiring va adminga xabar bering.",
        reply_markup=back_to_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("pay:"))
async def handle_payment(call: CallbackQuery, bot: Bot):
    _, action, req_id_str = call.data.split(":", 2)
    req_id = int(req_id_str)
    req = await db.get_payment_request(req_id)
    if not req:
        await call.answer("So'rov topilmadi.", show_alert=True)
        return
    if req["status"] != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return

    if action == "approve":
        await db.grant_paid_slot(req["user_id"])
        await db.set_payment_request_status(req_id, "approved")
        try:
            await bot.send_message(
                req["user_id"],
                "✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
                "Endi 1 ta qo'shimcha e'lon joylashtirish huquqingiz bor.\n"
                "Botga qayting va e'lon joylashtiring.",
                reply_markup=back_to_menu_kb(),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await call.message.edit_text(
            call.message.text + "\n\n✅ <b>Tasdiqlandi. Foydalanuvchiga 1 slot berildi.</b>",
            parse_mode="HTML"
        )

    elif action == "reject":
        await db.set_payment_request_status(req_id, "rejected")
        try:
            await bot.send_message(
                req["user_id"],
                "❌ <b>To'lov so'rovingiz rad etildi.</b>\n"
                "Muammo bo'lsa admin bilan bog'laning.",
                parse_mode="HTML"
            )
        except Exception:
            pass
        await call.message.edit_text(
            call.message.text + "\n\n❌ <b>Rad etildi.</b>",
            parse_mode="HTML"
        )


# ── Brand ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:brand:"))
async def sell_brand(call: CallbackQuery, state: FSMContext):
    brand = call.data.split(":", 2)[2]
    await state.update_data(brand=brand)
    await state.set_state(SellStates.model)
    await call.message.edit_text(
        f"✅ Rusm: <b>{brand}</b>\n\n📋 <b>Modelini tanlang:</b>",
        reply_markup=models_kb(brand, "sell"),
        parse_mode="HTML"
    )


# ── Model ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:model:"))
async def sell_model(call: CallbackQuery, state: FSMContext):
    model = call.data.split(":", 2)[2]
    await state.update_data(model=model)
    await state.set_state(SellStates.year)
    data = await state.get_data()
    await call.message.edit_text(
        f"✅ {data['brand']} <b>{model}</b>\n\n📅 <b>Ishlab chiqarilgan yilini tanlang:</b>",
        reply_markup=years_kb(),
        parse_mode="HTML"
    )


# ── Year ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:year:"))
async def sell_year(call: CallbackQuery, state: FSMContext):
    year_str = call.data.split(":", 2)[2]
    if year_str == "Eskiroq...":
        await state.update_data(year=MIN_YEAR)
        display = f"{MIN_YEAR} yilgacha"
    else:
        await state.update_data(year=int(year_str))
        display = year_str
    await state.set_state(SellStates.mileage)
    await call.message.edit_text(
        f"✅ Yil: <b>{display}</b>\n\n"
        f"🛣 <b>Yurgan masofasini kiriting (km):</b>\n"
        f"<i>Masalan: 85000   (0 – {MAX_MILEAGE:,} oralig'ida)</i>",
        parse_mode="HTML"
    )


# ── Mileage ────────────────────────────────────────────────────────────────────

@router.message(SellStates.mileage)
async def sell_mileage(message: Message, state: FSMContext):
    raw = message.text.strip().replace(" ", "").replace(",", "")
    if not raw.isdigit():
        await message.answer(
            "❌ Faqat raqam kiriting.\n<i>Masalan: 85000</i>",
            parse_mode="HTML"
        )
        return
    val = int(raw)
    if val > MAX_MILEAGE:
        await message.answer(
            f"❌ Juda katta qiymat. Maksimal: <b>{MAX_MILEAGE:,} km</b>\n"
            f"Agar masofa noto'g'ri bo'lsa tekshiring.",
            parse_mode="HTML"
        )
        return
    await state.update_data(mileage=val)
    await state.set_state(SellStates.price)
    await message.answer(
        f"✅ Masofa: <b>{val:,} km</b>\n\n"
        f"💰 <b>Narxini kiriting (USD):</b>\n"
        f"<i>Masalan: 12500   (${MIN_PRICE:,} – ${MAX_PRICE:,} oralig'ida)</i>",
        parse_mode="HTML"
    )


# ── Price ──────────────────────────────────────────────────────────────────────

@router.message(SellStates.price)
async def sell_price(message: Message, state: FSMContext):
    raw = message.text.strip().replace(" ", "").replace(",", "").replace("$", "")
    if not raw.isdigit():
        await message.answer(
            "❌ Faqat raqam kiriting.\n<i>Masalan: 12500</i>",
            parse_mode="HTML"
        )
        return
    val = int(raw)
    if val < MIN_PRICE:
        await message.answer(
            f"❌ Narx juda past. Minimal: <b>${MIN_PRICE:,}</b>\n"
            f"To'g'ri narxni kiriting.",
            parse_mode="HTML"
        )
        return
    if val > MAX_PRICE:
        await message.answer(
            f"❌ Narx juda yuqori. Maksimal: <b>${MAX_PRICE:,}</b>\n"
            f"Narxni USD da kiriting.",
            parse_mode="HTML"
        )
        return
    await state.update_data(price=val, currency="USD")
    await state.set_state(SellStates.city)
    await message.answer(
        f"✅ Narx: <b>${val:,}</b>\n\n📍 <b>Shaharni tanlang:</b>",
        reply_markup=cities_kb("sell"),
        parse_mode="HTML"
    )


# ── City ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:city:"))
async def sell_city(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":", 2)[2]
    await state.update_data(city=city, photos=[])
    await state.set_state(SellStates.phone)
    await call.message.answer(
        f"✅ Shahar: <b>{city}</b>\n\n"
        "📱 <b>Telefon raqamingizni yuboring</b>\n"
        "Xaridorlar siz bilan bog'lanishi uchun kerak.\n\n"
        "<i>Tugmani bosing yoki raqamni yozing: +998901234567</i>",
        reply_markup=phone_kb(),
        parse_mode="HTML"
    )


# ── Phone ──────────────────────────────────────────────────────────────────────

@router.message(SellStates.phone, F.contact)
async def sell_phone_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    await db.save_user_phone(message.from_user.id, phone)
    await _ask_photos(message, state)


@router.message(SellStates.phone, F.text)
async def sell_phone_text(message: Message, state: FSMContext):
    phone = message.text.strip()
    digits = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not digits.isdigit() or len(digits) < 9:
        await message.answer(
            "❌ Noto'g'ri raqam format.\n"
            "Masalan: <b>+998901234567</b>\n\n"
            "Yoki pastdagi tugmani bosing.",
            parse_mode="HTML"
        )
        return
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    await db.save_user_phone(message.from_user.id, phone)
    await _ask_photos(message, state)


async def _ask_photos(message: Message, state: FSMContext):
    await state.set_state(SellStates.photos)
    await message.answer(
        "✅ Telefon qabul qilindi.\n\n"
        f"📸 <b>Avtomobil rasmlarini yuboring</b>\n"
        f"Kamida <b>{MIN_PHOTOS} ta</b>, ko'pi bilan <b>{MAX_PHOTOS} ta</b>.\n\n"
        "Rasmlarni yuborib bo'lgach <b>Tayyor</b> tugmasini bosing.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    await message.answer("👇", reply_markup=photos_done_inline())


# ── Photos ─────────────────────────────────────────────────────────────────────

@router.message(SellStates.photos, F.photo)
async def sell_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos: list = data.get("photos", [])
    if len(photos) >= MAX_PHOTOS:
        await message.answer(f"⚠️ Maksimal {MAX_PHOTOS} ta rasm. Tayyor tugmasini bosing.")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    remaining = MIN_PHOTOS - len(photos)
    if remaining > 0:
        await message.answer(
            f"✅ {len(photos)} ta rasm qabul qilindi. Yana kamida <b>{remaining} ta</b> yuboring.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"✅ {len(photos)} ta rasm. Yana yuborishingiz yoki <b>Tayyor</b> bosishingiz mumkin.",
            reply_markup=photos_done_inline(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "sell:photos_done")
async def sell_photos_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) < MIN_PHOTOS:
        await call.answer(
            f"Kamida {MIN_PHOTOS} ta rasm kerak! Hozir {len(photos)} ta yuborildi.",
            show_alert=True
        )
        return
    await state.set_state(SellStates.description)
    await call.message.edit_text(
        f"✅ {len(photos)} ta rasm qabul qilindi.\n\n"
        "📝 <b>Qo'shimcha izoh (ixtiyoriy):</b>\n"
        "<i>Masalan: Bir egada bo'lgan, avariyasiz, konditsioner ishlaydi.</i>\n\n"
        "O'tkazib yuborish uchun <b>—</b> yuboring.",
        parse_mode="HTML"
    )


# ── Description ────────────────────────────────────────────────────────────────

@router.message(SellStates.description)
async def sell_description(message: Message, state: FSMContext):
    desc = None if message.text.strip() == "—" else message.text.strip()
    await state.update_data(description=desc)
    data = await state.get_data()

    listing_id = await db.create_listing(
        user_id=message.from_user.id,
        brand=data["brand"],
        model=data["model"],
        year=data["year"],
        mileage=data["mileage"],
        price=data["price"],
        currency=data["currency"],
        city=data["city"],
        description=desc,
        photo_file_ids=data["photos"],
        phone=data.get("phone", ""),
        is_paid=data.get("is_paid", False),
    )
    await state.update_data(draft_listing_id=listing_id)
    await state.set_state(SellStates.confirm)

    desc_line = f"📝 {desc}\n" if desc else ""
    paid_badge = "💳 To'langan e'lon\n" if data.get("is_paid") else "🆓 Bepul e'lon\n"
    preview = (
        f"🚗 <b>{data['brand']} {data['model']}, {data['year']}</b>\n"
        f"📍 {data['city']}   🛣 {data['mileage']:,} km\n"
        f"💰 <b>${data['price']:,}</b>\n"
        f"📱 {data.get('phone', '')}\n"
        f"{desc_line}"
        f"📸 {len(data['photos'])} ta rasm\n"
        f"{paid_badge}"
    )
    await message.answer(
        "📋 <b>E'loningizni tekshiring:</b>\n\n" + preview,
        reply_markup=confirm_listing_kb(listing_id),
        parse_mode="HTML"
    )


# ── Confirm ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("confirm:"))
async def sell_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    _, action, listing_id = call.data.split(":", 2)

    if action == "cancel":
        await db.set_listing_status(listing_id, "deleted")
        await state.clear()
        await call.message.edit_text("❌ E'lon bekor qilindi.", reply_markup=back_to_menu_kb())
        return

    if action == "edit":
        await db.set_listing_status(listing_id, "deleted")
        await state.clear()
        await call.message.edit_text("🔄 E'lonni qaytadan boshlaylik.", reply_markup=back_to_menu_kb())
        return

    if action == "publish":
        listing = await db.get_listing(listing_id)
        is_paid = listing.get("is_paid", False)

        # Consume the paid slot
        if is_paid:
            await db.use_paid_slot(call.from_user.id)

        desc_line = f"📝 {listing['description']}\n" if listing["description"] else ""
        paid_badge = "💳 <b>TO'LANGAN E'LON</b>\n" if is_paid else "🆓 Bepul e'lon\n"
        text = (
            f"🆕 <b>Yangi e'lon (tasdiqlash kerak)</b>\n"
            f"{paid_badge}\n"
            f"🚗 {listing['brand']} {listing['model']}, {listing['year']}\n"
            f"📍 {listing['city']}   🛣 {listing['mileage']:,} km\n"
            f"💰 ${listing['price']:,}\n"
            f"📱 {listing['phone']}\n"
            f"{desc_line}"
            f"👤 @{call.from_user.username or call.from_user.id}\n"
            f"🆔 <code>{listing_id}</code>"
        )
        from aiogram.types import InputMediaPhoto
        await bot.send_media_group(
            chat_id=ADMIN_ID,
            media=[InputMediaPhoto(media=fid) for fid in listing["photo_file_ids"]]
        )
        await bot.send_message(ADMIN_ID, text, reply_markup=admin_listing_kb(listing_id), parse_mode="HTML")
        await state.clear()
        await call.message.edit_text(
            "✅ <b>E'loningiz ko'rib chiqish uchun yuborildi!</b>\n"
            "Tasdiqlangandan so'ng e'loningiz faollashadi.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML"
        )
