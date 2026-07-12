import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

FREE_LISTING_LIMIT = 2
LISTING_EXPIRY_DAYS = 30
MIN_PHOTOS = 3
MAX_PHOTOS = 8
