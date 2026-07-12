from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from data.cars import BRANDS, BRANDS_MODELS, YEARS, CITIES


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔴 Sotish (Sell)", callback_data="sell")
    kb.button(text="🟢 Sotib olish (Buy)", callback_data="buy")
    kb.adjust(2)
    return kb.as_markup()


def brands_kb(prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for brand in BRANDS:
        kb.button(text=brand, callback_data=f"{prefix}:brand:{brand}")
    kb.adjust(2)
    return kb.as_markup()


def models_kb(brand: str, prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    models = BRANDS_MODELS.get(brand, ["Boshqa..."])
    for model in models:
        kb.button(text=model, callback_data=f"{prefix}:model:{model}")
    kb.adjust(2)
    return kb.as_markup()


def years_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for year in YEARS:
        kb.button(text=year, callback_data=f"sell:year:{year}")
    kb.adjust(3)
    return kb.as_markup()


def cities_kb(prefix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for city in CITIES:
        kb.button(text=city, callback_data=f"{prefix}:city:{city}")
    kb.adjust(2)
    return kb.as_markup()


def photos_done_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tayyor", callback_data="sell:photos_done")
    return kb.as_markup()


def confirm_listing_kb(listing_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ E'lon qilish", callback_data=f"confirm:publish:{listing_id}")
    kb.button(text="✏️ Tahrirlash",   callback_data=f"confirm:edit:{listing_id}")
    kb.button(text="❌ Bekor qilish", callback_data=f"confirm:cancel:{listing_id}")
    kb.adjust(1)
    return kb.as_markup()


def buy_filters_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Narx bo'yicha",   callback_data="buy:filter:price")
    kb.button(text="📅 Yil bo'yicha",    callback_data="buy:filter:year")
    kb.button(text="📍 Shahar bo'yicha", callback_data="buy:filter:city")
    kb.button(text="➡️ Hammasini ko'rsatish", callback_data="buy:filter:none")
    kb.adjust(1)
    return kb.as_markup()


def listing_nav_kb(index: int, total: int, listing_id: str, seller_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if index > 0:
        kb.button(text="◀️ Oldingi", callback_data=f"nav:prev:{index}")
    kb.button(text=f"{index+1}/{total}", callback_data="nav:count")
    if index < total - 1:
        kb.button(text="Keyingi ▶️", callback_data=f"nav:next:{index}")
    kb.button(text="✉️ Sotuvchiga yozish", url=f"tg://user?id={seller_id}")
    kb.button(text="⚠️ Shikoyat",          callback_data=f"report:{listing_id}")
    kb.button(text="🏠 Menyu",             callback_data="main_menu")
    kb.adjust(3, 1, 1, 1)
    return kb.as_markup()


def my_listings_item_kb(listing_id: str, status: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if status == "active":
        kb.button(text="✅ Sotildi",     callback_data=f"mylist:sold:{listing_id}")
        kb.button(text="🔄 Uzaytirish", callback_data=f"mylist:extend:{listing_id}")
    kb.button(text="🗑 O'chirish", callback_data=f"mylist:delete:{listing_id}")
    kb.button(text="◀️ Orqaga",   callback_data="mylist:back")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def admin_listing_kb(listing_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tasdiqlash",  callback_data=f"admin:approve:{listing_id}")
    kb.button(text="❌ Rad etish",   callback_data=f"admin:reject:{listing_id}")
    kb.adjust(2)
    return kb.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Asosiy menyu", callback_data="main_menu")
    return kb.as_markup()


def extend_kb(listing_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data=f"expire:extend:{listing_id}")
    kb.button(text="❌ Yo'q", callback_data=f"expire:no:{listing_id}")
    kb.adjust(2)
    return kb.as_markup()
