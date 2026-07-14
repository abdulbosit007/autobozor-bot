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

VALID_UZ_PREFIXES = ["90","91","93","94","95","97","98","99","33","71","78","77","88","55","50"]


class SellStates(StatesGroup):
    brand        = State()
    model        = State()
    year         = State()
    year_manual  = State()
    mileage      = State()
    price        = State()
    city         = State()
    phone        = State()
    photos       = State()
    description  = State()
    confirm      = State()
    share_tg = State()
    edit_choice  = State()   # rewrite or change params
    edit_param   = State()   # which param to change
    edit_mileage = State()
    edit_price   = State()
    edit_desc    = State()
    edit_phone   = State()
    edit_photos  = State()


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamimni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


def photos_done_inline():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tayyor", callback_data="sell:photos_done")
    return kb.as_markup()


def clean_number(text: str) -> str:
    """Strip spaces, commas, dots (used as thousand separators)."""
    return text.strip().replace(" ", "").replace(",", "").replace(".", "")


def validate_uz_phone(raw: str):
    """Returns normalized +998XXXXXXXXX or None. Also accepts @username."""
    raw = raw.strip()
    if raw.startswith("@"):
        if len(raw) >= 2:
            return raw  # telegram username — store as-is
        return None
    cleaned = raw.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("+998"):
        digits = cleaned[4:]
    elif cleaned.startswith("998"):
        digits = cleaned[3:]
    elif cleaned.startswith("8") and len(cleaned) == 10:
        digits = cleaned[1:]
    else:
        digits = cleaned
    if len(digits) != 9 or not digits.isdigit():
        return None
    if digits[:2] not in VALID_UZ_PREFIXES:
        return None
    return f"+998{digits}"


def phone_display(phone: str) -> str:
    if phone and phone.startswith("@"):
        return f'<a href="https://t.me/{phone[1:]}">{phone}</a>'
    return phone or ""


# ── Entry ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sell")
async def sell_start(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    count = await db.count_active_listings(user_id)
    user = await db.get_user(user_id)

    if count >= FREE_LISTING_LIMIT:
        paid_slots = user.get("paid_slots", 0) or 0
        if paid_slots > 0:
            await state.update_data(is_paid=True)
        else:
            kb = InlineKeyboardBuilder()
            kb.button(text="💳 To'lov so'rovi yuborish", callback_data="sell:pay_request")
            kb.button(text="🏠 Menyu", callback_data="main_menu")
            kb.adjust(1)
            await call.message.edit_text(
                f"⚠️ Sizda allaqachon <b>{count} ta</b> faol e'lon bor.\n\n"
                f"Bepul limit: <b>{FREE_LISTING_LIMIT} ta</b>\n\n"
                "Qo'shimcha e'lon joylashtirish uchun <b>har bir e'lon uchun to'lov</b> talab qilinadi.\n"
                "To'lov so'rovi yuboring — admin to'lovni tasdiqlaydi.",
                reply_markup=kb.as_markup(), parse_mode="HTML"
            )
            return
    else:
        await state.update_data(is_paid=False)

    await state.set_state(SellStates.brand)
    await call.message.edit_text(
        "🚗 <b>Avtomobil rusumini tanlang:</b>",
        reply_markup=brands_kb("sell"), parse_mode="HTML"
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
        f"👤 @{username}\n📱 {user_phone}\n"
        f"🆔 <code>{call.from_user.id}</code>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await call.message.edit_text(
        "✅ <b>So'rovingiz adminga yuborildi.</b>\n\n"
        "Admin to'lovni tasdiqlashi bilan sizga xabar keladi.",
        reply_markup=back_to_menu_kb(), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("pay:"))
async def handle_payment(call: CallbackQuery, bot: Bot):
    _, action, req_id_str = call.data.split(":", 2)
    req = await db.get_payment_request(int(req_id_str))
    if not req or req["status"] != "pending":
        await call.answer("Bu so'rov allaqachon ko'rib chiqilgan.", show_alert=True)
        return
    if action == "approve":
        await db.grant_paid_slot(req["user_id"])
        await db.set_payment_request_status(int(req_id_str), "approved")
        try:
            await bot.send_message(
                req["user_id"],
                "✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
                "Endi 1 ta qo'shimcha e'lon joylashtirish huquqingiz bor.\n"
                "Botga qayting va e'lon joylashtiring.",
                reply_markup=back_to_menu_kb(), parse_mode="HTML"
            )
        except Exception:
            pass
        await call.message.edit_text(call.message.text + "\n\n✅ <b>Tasdiqlandi.</b>", parse_mode="HTML")
    else:
        await db.set_payment_request_status(int(req_id_str), "rejected")
        try:
            await bot.send_message(req["user_id"], "❌ <b>To'lov so'rovingiz rad etildi.</b>", parse_mode="HTML")
        except Exception:
            pass
        await call.message.edit_text(call.message.text + "\n\n❌ <b>Rad etildi.</b>", parse_mode="HTML")


# ── Brand ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:brand:"))
async def sell_brand(call: CallbackQuery, state: FSMContext):
    brand = call.data.split(":", 2)[2]
    await state.update_data(brand=brand)
    await state.set_state(SellStates.model)
    await call.message.edit_text(
        f"✅ Rusm: <b>{brand}</b>\n\n📋 <b>Modelini tanlang:</b>",
        reply_markup=models_kb(brand, "sell"), parse_mode="HTML"
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
        reply_markup=years_kb(), parse_mode="HTML"
    )


# ── Year ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:year:"))
async def sell_year(call: CallbackQuery, state: FSMContext):
    year_str = call.data.split(":", 2)[2]
    if year_str == "Eskiroq...":
        await state.set_state(SellStates.year_manual)
        await call.message.edit_text(
            f"📅 <b>Ishlab chiqarilgan yilini kiriting:</b>\n"
            f"<i>{MIN_YEAR} – {CURRENT_YEAR - 9} oralig'ida</i>\n\nMasalan: <b>2008</b>",
            parse_mode="HTML"
        )
        return
    await state.update_data(year=int(year_str))
    await _ask_mileage(call.message, state, year_str, edit=False)


@router.message(SellStates.year_manual)
async def sell_year_manual(message: Message, state: FSMContext):
    raw = clean_number(message.text)
    if not raw.isdigit():
        await message.answer("❌ Faqat raqam kiriting.\n<i>Masalan: 2008</i>", parse_mode="HTML")
        return
    year = int(raw)
    if year < MIN_YEAR or year > CURRENT_YEAR:
        await message.answer(
            f"❌ Yil <b>{MIN_YEAR}</b> – <b>{CURRENT_YEAR}</b> oralig'ida bo'lishi kerak.",
            parse_mode="HTML"
        )
        return
    await state.update_data(year=year)
    await _ask_mileage(message, state, str(year), edit=False)


async def _ask_mileage(target, state, year_display, edit=False):
    await state.set_state(SellStates.edit_mileage if edit else SellStates.mileage)
    text = (
        f"✅ Yil: <b>{year_display}</b>\n\n"
        f"🛣 <b>Yurgan masofasini kiriting (km):</b>\n"
        f"<i>Masalan: 85000   (0 – {MAX_MILEAGE:,} oralig'ida)</i>"
    )
    if isinstance(target, Message):
        await target.answer(text, parse_mode="HTML")
    else:
        await target.edit_text(text, parse_mode="HTML")


# ── Mileage ────────────────────────────────────────────────────────────────────

async def _process_mileage(message: Message, state: FSMContext, editing: bool):
    raw = clean_number(message.text)
    if not raw.isdigit():
        await message.answer(
            "❌ Faqat raqam kiriting. Nuqta/vergul ishlatmang.\n<i>Masalan: 85000</i>",
            parse_mode="HTML"
        )
        return False
    val = int(raw)
    if val > MAX_MILEAGE:
        await message.answer(
            f"❌ Juda katta qiymat. Maksimal: <b>{MAX_MILEAGE:,} km</b>",
            parse_mode="HTML"
        )
        return False
    await state.update_data(mileage=val)
    return True


@router.message(SellStates.mileage)
async def sell_mileage(message: Message, state: FSMContext):
    if not await _process_mileage(message, state, editing=False):
        return
    data = await state.get_data()
    await state.set_state(SellStates.price)
    await message.answer(
        f"✅ Masofa: <b>{data['mileage']:,} km</b>\n\n"
        f"💰 <b>Narxini kiriting (USD):</b>\n"
        f"<i>Masalan: 12500   (${MIN_PRICE:,} – ${MAX_PRICE:,} oralig'ida)</i>",
        parse_mode="HTML"
    )


@router.message(SellStates.edit_mileage)
async def edit_mileage(message: Message, state: FSMContext):
    if not await _process_mileage(message, state, editing=True):
        return
    await _show_confirm(message, state)


# ── Price ──────────────────────────────────────────────────────────────────────

async def _process_price(message: Message, state: FSMContext):
    raw = clean_number(message.text).replace("$", "")
    if not raw.isdigit():
        await message.answer(
            "❌ Faqat raqam kiriting. Nuqta/vergul ishlatmang.\n<i>Masalan: 12500</i>",
            parse_mode="HTML"
        )
        return False
    val = int(raw)
    if val < MIN_PRICE:
        await message.answer(
            f"❌ Narx juda past. Minimal: <b>${MIN_PRICE:,}</b>",
            parse_mode="HTML"
        )
        return False
    if val > MAX_PRICE:
        await message.answer(
            f"❌ Narx juda yuqori. Maksimal: <b>${MAX_PRICE:,}</b>",
            parse_mode="HTML"
        )
        return False
    await state.update_data(price=val, currency="USD")
    return True


@router.message(SellStates.price)
async def sell_price(message: Message, state: FSMContext):
    if not await _process_price(message, state):
        return
    data = await state.get_data()
    await state.set_state(SellStates.city)
    await message.answer(
        f"✅ Narx: <b>${data['price']:,}</b>\n\n📍 <b>Shaharni tanlang:</b>",
        reply_markup=cities_kb("sell"), parse_mode="HTML"
    )


@router.message(SellStates.edit_price)
async def edit_price(message: Message, state: FSMContext):
    if not await _process_price(message, state):
        return
    await _show_confirm(message, state)


# ── City ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:city:"))
async def sell_city(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":", 2)[2]
    await state.update_data(city=city, photos=[])
    await state.set_state(SellStates.phone)
    await call.message.answer(
        f"✅ Shahar: <b>{city}</b>\n\n"
        "📱 <b>Telefon raqam yoki Telegram username kiriting:</b>\n\n"
        "• Uzbek raqam: <b>901234567</b> yoki <b>+998901234567</b>\n"
        "• Telegram: <b>@username</b>\n\n"
        "Yoki pastdagi tugmani bosing:",
        reply_markup=phone_kb(), parse_mode="HTML"
    )


# ── Phone ──────────────────────────────────────────────────────────────────────

async def _process_phone(message: Message, state: FSMContext, editing: bool):
    raw = message.text.strip() if message.text else None
    if message.contact:
        raw = message.contact.phone_number

    result = validate_uz_phone(raw or "")
    if result is None:
        await message.answer(
            "❌ Noto'g'ri format.\n\n"
            "Quyidagilardan birini kiriting:\n"
            "• <b>901234567</b> — 9 raqam (prefiks: 90,91,93,94,95,97,98,99,33,71,78,77,88,55,50)\n"
            "• <b>+998901234567</b>\n"
            "• <b>@username</b> — Telegram username\n\n"
            "Yoki pastdagi tugmani bosing.",
            parse_mode="HTML"
        )
        return False
    await state.update_data(phone=result)
    await db.save_user_phone(message.from_user.id, result)
    return True


@router.message(SellStates.phone, F.contact)
async def sell_phone_contact(message: Message, state: FSMContext):
    if not await _process_phone(message, state, editing=False):
        return
    await _ask_share_tg(message, state)


@router.message(SellStates.phone, F.text)
async def sell_phone_text(message: Message, state: FSMContext):
    if not await _process_phone(message, state, editing=False):
        return
    await _ask_share_tg(message, state)


async def _ask_share_tg(message: Message, state: FSMContext):
    await state.set_state(SellStates.share_tg)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, ulashaman", callback_data="sell:tg:yes")
    kb.button(text="❌ Yo'q",          callback_data="sell:tg:no")
    kb.adjust(2)
    await message.answer(
        "📲 <b>Telegram orqali ham bog'lanish imkonini bermoqchimisiz?</b>\n\n"
        "Ha desangiz, xaridorlar sizga to'g'ridan-to'g'ri Telegram orqali yozishlari mumkin bo'ladi.",
        reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
    )
    await message.answer("👇", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("sell:tg:"))
async def sell_share_tg(call: CallbackQuery, state: FSMContext):
    if call.data == "sell:tg:yes":
        await state.update_data(tg_user_id=call.from_user.id)
    else:
        await state.update_data(tg_user_id=None)
    await call.message.edit_reply_markup(reply_markup=None)
    await _ask_photos(call.message, state)


@router.message(SellStates.edit_phone, F.contact)
async def edit_phone_contact(message: Message, state: FSMContext):
    if not await _process_phone(message, state, editing=True):
        return
    await message.answer("✅ Telefon yangilandi.", reply_markup=ReplyKeyboardRemove())
    await _show_confirm(message, state)


@router.message(SellStates.edit_phone, F.text)
async def edit_phone_text(message: Message, state: FSMContext):
    if not await _process_phone(message, state, editing=True):
        return
    await message.answer("✅ Telefon yangilandi.", reply_markup=ReplyKeyboardRemove())
    await _show_confirm(message, state)


async def _ask_photos(message: Message, state: FSMContext):
    await state.set_state(SellStates.photos)
    await message.answer(
        f"📸 <b>Avtomobil rasmlarini yuboring</b>\n"
        f"Kamida <b>{MIN_PHOTOS} ta</b>, ko'pi bilan <b>{MAX_PHOTOS} ta</b>.\n\n"
        "Rasmlarni yuborib bo'lgach <b>Tayyor</b> tugmasini bosing.",
        parse_mode="HTML"
    )
    await message.answer("👇", reply_markup=photos_done_inline())


# ── Photos ─────────────────────────────────────────────────────────────────────

@router.message(SellStates.photos, F.photo)
@router.message(SellStates.edit_photos, F.photo)
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
        await message.answer(f"✅ {len(photos)} ta rasm. Yana kamida <b>{remaining} ta</b> yuboring.", parse_mode="HTML")
    else:
        await message.answer(
            f"✅ {len(photos)} ta rasm. Yana yuborishingiz yoki <b>Tayyor</b> bosishingiz mumkin.",
            reply_markup=photos_done_inline(), parse_mode="HTML"
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
    current = await state.get_state()
    if current == SellStates.edit_photos:
        await call.message.edit_text("✅ Rasmlar yangilandi.")
        await _show_confirm(call.message, state)
    else:
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
        brand=data["brand"], model=data["model"], year=data["year"],
        mileage=data["mileage"], price=data["price"], currency=data["currency"],
        city=data["city"], description=desc,
        photo_file_ids=data["photos"], phone=data.get("phone", ""),
        tg_user_id=data.get("tg_user_id"),
        is_paid=data.get("is_paid", False),
    )
    await state.update_data(draft_listing_id=listing_id)
    await state.set_state(SellStates.confirm)
    await _show_confirm(message, state)


@router.message(SellStates.edit_desc)
async def edit_desc(message: Message, state: FSMContext):
    desc = None if message.text.strip() == "—" else message.text.strip()
    await state.update_data(description=desc)
    await _show_confirm(message, state)


# ── Confirm & Edit loop ────────────────────────────────────────────────────────

async def _show_confirm(target, state: FSMContext):
    await state.set_state(SellStates.confirm)
    data = await state.get_data()
    phone = data.get("phone", "")
    tg_user_id = data.get("tg_user_id")
    tg_line = f"💬 Telegram: ulashilgan\n" if tg_user_id else ""
    desc_line = f"📝 {data.get('description')}\n" if data.get("description") else ""
    paid_badge = "💳 To'langan e'lon\n" if data.get("is_paid") else "🆓 Bepul e'lon\n"
    preview = (
        f"🚗 <b>{data['brand']} {data['model']}, {data['year']}</b>\n"
        f"📍 {data['city']}   🛣 {data['mileage']:,} km\n"
        f"💰 <b>${data['price']:,}</b>\n"
        f"📱 {phone}\n"
        f"{tg_line}"
        f"{desc_line}"
        f"📸 {len(data.get('photos', []))} ta rasm\n"
        f"{paid_badge}"
    )
    listing_id = data.get("draft_listing_id", "")
    text = "📋 <b>E'loningizni tekshiring:</b>\n\n" + preview
    if isinstance(target, Message):
        await target.answer(text, reply_markup=confirm_listing_kb(listing_id), parse_mode="HTML")
    else:
        try:
            await target.edit_text(text, reply_markup=confirm_listing_kb(listing_id), parse_mode="HTML")
        except Exception:
            await target.answer(text, reply_markup=confirm_listing_kb(listing_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("confirm:"))
async def sell_confirm(call: CallbackQuery, state: FSMContext, bot: Bot):
    _, action, listing_id = call.data.split(":", 2)

    if action == "cancel":
        await db.set_listing_status(listing_id, "deleted")
        await state.clear()
        await call.message.edit_text("❌ E'lon bekor qilindi.", reply_markup=back_to_menu_kb())
        return

    if action == "edit":
        await state.set_state(SellStates.edit_choice)
        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Qaytadan yozish",       callback_data="edit:rewrite")
        kb.button(text="✏️ Parametr o'zgartirish", callback_data="edit:params")
        kb.adjust(1)
        await call.message.edit_text(
            "✏️ <b>Qanday o'zgartirishni xohlaysiz?</b>",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
        return

    if action == "publish":
        listing = await db.get_listing(listing_id)
        # Sync current state data into the DB listing before publishing
        data = await state.get_data()
        await db.update_listing_fields(listing_id, data)
        listing = await db.get_listing(listing_id)

        if listing.get("is_paid"):
            await db.use_paid_slot(call.from_user.id)

        desc_line = f"📝 {listing['description']}\n" if listing.get("description") else ""
        paid_badge = "💳 <b>TO'LANGAN E'LON</b>\n" if listing.get("is_paid") else "🆓 Bepul e'lon\n"
        text = (
            f"🆕 <b>Yangi e'lon (tasdiqlash kerak)</b>\n{paid_badge}\n"
            f"🚗 {listing['brand']} {listing['model']}, {listing['year']}\n"
            f"📍 {listing['city']}   🛣 {listing['mileage']:,} km\n"
            f"💰 ${listing['price']:,}\n"
            f"📱 {listing.get('phone','')}\n"
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
            reply_markup=back_to_menu_kb(), parse_mode="HTML"
        )


# ── Edit choice ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "edit:rewrite")
async def edit_rewrite(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    listing_id = data.get("draft_listing_id")
    if listing_id:
        await db.set_listing_status(listing_id, "deleted")
    is_paid = data.get("is_paid", False)
    await state.clear()
    await state.update_data(is_paid=is_paid)
    await state.set_state(SellStates.brand)
    await call.message.edit_text(
        "🔄 <b>Qaytadan boshlaymiz.</b>\n\n🚗 <b>Avtomobil rusumini tanlang:</b>",
        reply_markup=brands_kb("sell"), parse_mode="HTML"
    )


@router.callback_query(F.data == "edit:params")
async def edit_params(call: CallbackQuery, state: FSMContext):
    await state.set_state(SellStates.edit_param)
    kb = InlineKeyboardBuilder()
    params = [
        ("🛣 Masofa",    "mileage"),
        ("💰 Narx",      "price"),
        ("📍 Shahar",    "city"),
        ("📱 Telefon",   "phone"),
        ("📸 Rasmlar",   "photos"),
        ("📝 Izoh",      "desc"),
    ]
    for label, key in params:
        kb.button(text=label, callback_data=f"editp:{key}")
    kb.button(text="✅ Tasdiqlashga qaytish", callback_data="editp:back")
    kb.adjust(2, 2, 2, 1)
    await call.message.edit_text(
        "✏️ <b>Qaysi parametrni o'zgartirmoqchisiz?</b>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("editp:"))
async def edit_param_chosen(call: CallbackQuery, state: FSMContext):
    param = call.data.split(":", 1)[1]

    if param == "back":
        await _show_confirm(call.message, state)
        return

    if param == "mileage":
        await state.set_state(SellStates.edit_mileage)
        await call.message.edit_text(
            f"🛣 <b>Yangi masofani kiriting (km):</b>\n"
            f"<i>0 – {MAX_MILEAGE:,} oralig'ida</i>", parse_mode="HTML"
        )
    elif param == "price":
        await state.set_state(SellStates.edit_price)
        await call.message.edit_text(
            f"💰 <b>Yangi narxni kiriting (USD):</b>\n"
            f"<i>${MIN_PRICE:,} – ${MAX_PRICE:,} oralig'ida</i>", parse_mode="HTML"
        )
    elif param == "city":
        await call.message.edit_text(
            "📍 <b>Yangi shaharni tanlang:</b>",
            reply_markup=cities_kb("editcity"), parse_mode="HTML"
        )
    elif param == "phone":
        await state.set_state(SellStates.edit_phone)
        await call.message.answer(
            "📱 <b>Yangi telefon yoki @username kiriting:</b>\n"
            "• <b>901234567</b> yoki <b>+998901234567</b>\n"
            "• <b>@username</b>",
            reply_markup=phone_kb(), parse_mode="HTML"
        )
    elif param == "photos":
        await state.update_data(photos=[])
        await state.set_state(SellStates.edit_photos)
        await call.message.edit_text(
            f"📸 <b>Yangi rasmlarni yuboring</b>\n"
            f"Kamida {MIN_PHOTOS} ta, ko'pi bilan {MAX_PHOTOS} ta.\n\n"
            "Tayyor bo'lgach <b>Tayyor</b> tugmasini bosing.",
            parse_mode="HTML"
        )
        await call.message.answer("👇", reply_markup=photos_done_inline())
    elif param == "desc":
        await state.set_state(SellStates.edit_desc)
        await call.message.edit_text(
            "📝 <b>Yangi izoh kiriting:</b>\n"
            "O'chirish uchun <b>—</b> yuboring.", parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("editcity:"))
async def edit_city_chosen(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":", 1)[1]
    await state.update_data(city=city)
    await _show_confirm(call.message, state)
