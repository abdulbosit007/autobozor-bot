from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db
from keyboards.kb import (
    brands_kb, models_kb, buy_filters_kb, cities_kb,
    listing_nav_kb, back_to_menu_kb
)

router = Router()


class BuyStates(StatesGroup):
    brand        = State()
    model        = State()
    filter_mode  = State()
    filter_input = State()
    browsing     = State()


# ── Entry ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "buy")
async def buy_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(BuyStates.brand)
    await call.message.edit_text(
        "🔍 <b>Qaysi rusum avtomobilni qidiryapsiz?</b>",
        reply_markup=brands_kb("buy"),
        parse_mode="HTML"
    )


# ── Brand ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("buy:brand:"))
async def buy_brand(call: CallbackQuery, state: FSMContext):
    brand = call.data.split(":", 2)[2]
    await state.update_data(brand=brand, filters={})
    await state.set_state(BuyStates.model)
    await call.message.edit_text(
        f"✅ <b>{brand}</b>\n\n📋 <b>Modelini tanlang:</b>",
        reply_markup=models_kb(brand, "buy"),
        parse_mode="HTML"
    )


# ── Model ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("buy:model:"))
async def buy_model(call: CallbackQuery, state: FSMContext):
    model = call.data.split(":", 2)[2]
    await state.update_data(model=model)
    await state.set_state(BuyStates.filter_mode)
    await call.message.edit_text(
        "🔧 <b>Filtrlash (ixtiyoriy):</b>",
        reply_markup=buy_filters_kb(),
        parse_mode="HTML"
    )


# ── Filters ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "buy:filter:none")
async def buy_no_filter(call: CallbackQuery, state: FSMContext):
    await _show_results(call, state, index=0)


@router.callback_query(F.data == "buy:filter:city")
async def buy_filter_city(call: CallbackQuery, state: FSMContext):
    await state.update_data(pending_filter="city")
    await state.set_state(BuyStates.filter_input)
    await call.message.edit_text(
        "📍 <b>Shaharniy tanlang:</b>",
        reply_markup=cities_kb("buyf"),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("buyf:city:"))
async def buy_filter_city_chosen(call: CallbackQuery, state: FSMContext):
    city = call.data.split(":", 2)[2]
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["city"] = city
    await state.update_data(filters=filters)
    await state.set_state(BuyStates.filter_mode)
    await call.message.edit_text(
        f"✅ Shahar: <b>{city}</b>\n\n🔧 <b>Boshqa filter:</b>",
        reply_markup=buy_filters_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "buy:filter:price")
async def buy_filter_price(call: CallbackQuery, state: FSMContext):
    await state.update_data(pending_filter="price")
    await state.set_state(BuyStates.filter_input)
    await call.message.edit_text(
        "💰 <b>Narx oraliqini kiriting (USD):</b>\n"
        "<i>Masalan: 5000-15000</i>",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "buy:filter:year")
async def buy_filter_year(call: CallbackQuery, state: FSMContext):
    await state.update_data(pending_filter="year")
    await state.set_state(BuyStates.filter_input)
    await call.message.edit_text(
        "📅 <b>Yil oraliqini kiriting:</b>\n"
        "<i>Masalan: 2018-2022</i>",
        parse_mode="HTML"
    )


@router.message(BuyStates.filter_input)
async def buy_filter_text(message: Message, state: FSMContext):
    data = await state.get_data()
    pf = data.get("pending_filter", "")
    filters = data.get("filters", {})
    text = message.text.strip()

    if pf in ("price", "year"):
        parts = text.replace(" ", "").split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            lo, hi = int(parts[0]), int(parts[1])
            if pf == "price":
                filters["min_price"] = lo
                filters["max_price"] = hi
            else:
                filters["min_year"] = lo
                filters["max_year"] = hi
        else:
            await message.answer("❌ Format xato. Masalan: <b>5000-15000</b>", parse_mode="HTML")
            return

    await state.update_data(filters=filters)
    await state.set_state(BuyStates.filter_mode)
    await message.answer(
        "✅ Filter qo'shildi.\n\n🔧 <b>Boshqa filter qo'shish yoki natijalarni ko'rish:</b>",
        reply_markup=buy_filters_kb(),
        parse_mode="HTML"
    )


# ── Navigation ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("nav:"))
async def navigate(call: CallbackQuery, state: FSMContext):
    _, direction, idx_str = call.data.split(":", 2)
    if direction == "count":
        await call.answer()
        return
    current = int(idx_str)
    new_index = current - 1 if direction == "prev" else current + 1
    await _show_results(call, state, index=new_index)


async def _show_results(call: CallbackQuery, state: FSMContext, index: int):
    data = await state.get_data()
    filters = data.get("filters", {})

    listings = await db.search_listings(
        brand=data["brand"],
        model=data["model"],
        min_price=filters.get("min_price"),
        max_price=filters.get("max_price"),
        min_year=filters.get("min_year"),
        max_year=filters.get("max_year"),
        city=filters.get("city"),
    )

    if not listings:
        await call.message.edit_text(
            "😔 <b>Hech qanday e'lon topilmadi.</b>\n\nBoshqa model yoki filtrsiz urinib ko'ring.",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML"
        )
        return

    total = len(listings)
    index = max(0, min(index, total - 1))
    listing = listings[index]

    desc_line = f"📝 {listing['description']}\n" if listing["description"] else ""
    caption = (
        f"🚗 <b>{listing['brand']} {listing['model']}, {listing['year']}</b>\n"
        f"📍 {listing['city']}   🛣 {listing['mileage']:,} km\n"
        f"💰 <b>${listing['price']:,}</b>\n"
        f"{desc_line}"
        f"📸 {len(listing['photo_file_ids'])} ta rasm\n\n"
        f"👤 Sotuvchi: tg://user?id={listing['user_id']}"
    )

    nav_kb = listing_nav_kb(index, total, str(listing["listing_id"]), listing["user_id"])

    photos = listing["photo_file_ids"]
    try:
        if len(photos) == 1:
            await call.message.edit_text("⏳ Yuklanmoqda...")
            await call.message.answer_photo(photos[0], caption=caption, parse_mode="HTML", reply_markup=nav_kb)
        else:
            media = [InputMediaPhoto(media=pid) for pid in photos]
            media[0] = InputMediaPhoto(media=photos[0], caption=caption, parse_mode="HTML")
            await call.message.answer_media_group(media)
            await call.message.answer("Navigatsiya:", reply_markup=nav_kb)
        await call.message.delete()
    except Exception:
        await call.message.edit_text(caption, reply_markup=nav_kb, parse_mode="HTML")


# ── Report ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("report:"))
async def report_listing(call: CallbackQuery):
    listing_id = call.data.split(":", 1)[1]
    count = await db.add_report(listing_id, call.from_user.id)
    await call.answer(f"✅ Shikoyat yuborildi. (Jami: {count})", show_alert=True)
