from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import FREE_LISTING_LIMIT, MIN_PHOTOS, MAX_PHOTOS, ADMIN_ID, CHANNEL_ID
from database import db
from keyboards.kb import (
    brands_kb, models_kb, years_kb, cities_kb,
    photos_done_kb, confirm_listing_kb, back_to_menu_kb, admin_listing_kb
)

router = Router()


class SellStates(StatesGroup):
    brand       = State()
    model       = State()
    year        = State()
    mileage     = State()
    price       = State()
    city        = State()
    photos      = State()
    description = State()
    confirm     = State()


# ── Entry ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "sell")
async def sell_start(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    count = await db.count_active_listings(user_id)
    user = await db.get_user(user_id)
    if count >= FREE_LISTING_LIMIT and not user["is_dealer"]:
        await call.message.edit_text(
            "⚠️ Siz allaqachon <b>2 ta bepul e'lon</b> joylashtirdingiz.\n"
            "Ko'proq joylashtirish uchun dealer hisobi kerak.\n\n"
            "📩 Admin bilan bog'laning: @autobozor_admin",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML"
        )
        return

    await state.set_state(SellStates.brand)
    await call.message.edit_text(
        "🚗 <b>Avtomobil rusumini tanlang:</b>",
        reply_markup=brands_kb("sell"),
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
        await state.update_data(year=2015)
    else:
        await state.update_data(year=int(year_str))
    await state.set_state(SellStates.mileage)
    await call.message.edit_text(
        f"✅ Yil: <b>{year_str}</b>\n\n"
        "🛣 <b>Yurgan masofasini kiriting (km):</b>\n"
        "<i>Masalan: 85000</i>",
        parse_mode="HTML"
    )


# ── Mileage ────────────────────────────────────────────────────────────────────

@router.message(SellStates.mileage)
async def sell_mileage(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "").replace(",", "")
    if not text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting. Masalan: <b>85000</b>", parse_mode="HTML")
        return
    await state.update_data(mileage=int(text))
    await state.set_state(SellStates.price)
    await message.answer(
        f"✅ Masofa: <b>{int(text):,} km</b>\n\n"
        "💰 <b>Narxini kiriting (USD):</b>\n"
        "<i>Masalan: 12500</i>",
        parse_mode="HTML"
    )


# ── Price ──────────────────────────────────────────────────────────────────────

@router.message(SellStates.price)
async def sell_price(message: Message, state: FSMContext):
    text = message.text.strip().replace(" ", "").replace(",", "").replace("$", "").replace("£", "")
    if not text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting. Masalan: <b>12500</b>", parse_mode="HTML")
        return
    await state.update_data(price=int(text), currency="USD")
    await state.set_state(SellStates.city)
    await message.answer(
        f"✅ Narx: <b>${int(text):,}</b>\n\n📍 <b>Shaharni tanlang:</b>",
        reply_markup=cities_kb("sell"),
        parse_mode="HTML"
    )


# ── City ───────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sell:city:"))
async def sell_city(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":", 2)[2]
    await state.update_data(city=city)
    await state.update_data(photos=[])
    await state.set_state(SellStates.photos)
    await call.message.edit_text(
        f"✅ Shahar: <b>{city}</b>\n\n"
        f"📸 <b>Avtomobil rasmlarini yuboring</b>\n"
        f"Kamida {MIN_PHOTOS} ta, ko'pi bilan {MAX_PHOTOS} ta.\n\n"
        f"Rasmlarni yuborib bo'lgach <b>Tayyor</b> tugmasini bosing.",
        reply_markup=photos_done_kb(),
        parse_mode="HTML"
    )


# ── Photos ─────────────────────────────────────────────────────────────────────

@router.message(SellStates.photos, F.photo)
async def sell_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos: list = data.get("photos", [])
    if len(photos) >= MAX_PHOTOS:
        await message.answer(f"⚠️ Maksimal {MAX_PHOTOS} ta rasm yuborishingiz mumkin.")
        return
    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    remaining = MIN_PHOTOS - len(photos)
    if remaining > 0:
        await message.answer(
            f"✅ {len(photos)} ta rasm qabul qilindi. Yana kamida {remaining} ta yuboring.",
            reply_markup=photos_done_kb()
        )
    else:
        await message.answer(
            f"✅ {len(photos)} ta rasm. Yana yuborishingiz yoki <b>Tayyor</b> bosishingiz mumkin.",
            reply_markup=photos_done_kb(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "sell:photos_done")
async def sell_photos_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    if len(photos) < MIN_PHOTOS:
        await call.answer(f"Kamida {MIN_PHOTOS} ta rasm kerak! ({len(photos)} ta yuborildi)", show_alert=True)
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
        description=data.get("description"),
        photo_file_ids=data["photos"],
    )
    await state.update_data(draft_listing_id=listing_id)
    await state.set_state(SellStates.confirm)

    desc_line = f"📝 {desc}" if desc else ""
    preview = (
        f"🚗 <b>{data['brand']} {data['model']}, {data['year']}</b>\n"
        f"📍 {data['city']}   🛣 {data['mileage']:,} km\n"
        f"💰 <b>${data['price']:,}</b>\n"
        f"{desc_line}\n"
        f"📸 {len(data['photos'])} ta rasm"
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
        await call.message.edit_text(
            "🔄 E'lonni qaytadan boshlaylik.",
            reply_markup=back_to_menu_kb()
        )
        return

    if action == "publish":
        listing = await db.get_listing(listing_id)
        # Send for admin approval
        desc_line = f"📝 {listing['description']}\n" if listing["description"] else ""
        text = (
            f"🆕 <b>Yangi e'lon (tasdiqlash kerak)</b>\n\n"
            f"🚗 {listing['brand']} {listing['model']}, {listing['year']}\n"
            f"📍 {listing['city']}   🛣 {listing['mileage']:,} km\n"
            f"💰 ${listing['price']:,}\n"
            f"{desc_line}"
            f"👤 Sotuvchi: @{call.from_user.username or call.from_user.id}\n"
            f"🆔 ID: <code>{listing_id}</code>"
        )
        await bot.send_media_group(
            chat_id=ADMIN_ID,
            media=[
                __import__("aiogram").types.InputMediaPhoto(media=fid)
                for fid in listing["photo_file_ids"]
            ]
        )
        await bot.send_message(ADMIN_ID, text, reply_markup=admin_listing_kb(listing_id), parse_mode="HTML")
        await state.clear()
        await call.message.edit_text(
            "✅ <b>E'loningiz ko'rib chiqish uchun yuborildi!</b>\n"
            "Tasdiqlangandan so'ng e'loningiz faollashadi.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML"
        )
