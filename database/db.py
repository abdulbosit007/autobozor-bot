import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from config import DATABASE_URL

_pool: AsyncConnectionPool = None


async def init_db():
    global _pool
    _pool = AsyncConnectionPool(DATABASE_URL, open=False, kwargs={"row_factory": dict_row})
    await _pool.open()
    await create_tables()


async def create_tables():
    async with _pool.connection() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     BIGINT PRIMARY KEY,
                username    TEXT,
                phone       TEXT,
                is_dealer   BOOLEAN DEFAULT FALSE,
                paid_slots  INT DEFAULT 0,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_slots INT DEFAULT 0")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                listing_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id         BIGINT REFERENCES users(user_id),
                brand           TEXT NOT NULL,
                model           TEXT NOT NULL,
                year            INT NOT NULL,
                mileage         INT NOT NULL,
                price           BIGINT NOT NULL,
                currency        TEXT NOT NULL DEFAULT 'USD',
                city            TEXT NOT NULL,
                description     TEXT,
                phone           TEXT,
                photo_file_ids  TEXT[] NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                is_paid         BOOLEAN DEFAULT FALSE,
                is_featured     BOOLEAN DEFAULT FALSE,
                channel_msg_id  BIGINT,
                created_at      TIMESTAMP DEFAULT NOW(),
                expires_at      TIMESTAMP DEFAULT NOW() + INTERVAL '30 days'
            )
        """)
        await conn.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS phone TEXT")
        await conn.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE")
        await conn.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS was_approved BOOLEAN DEFAULT FALSE")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_requests (
                id          SERIAL PRIMARY KEY,
                user_id     BIGINT REFERENCES users(user_id),
                username    TEXT,
                user_phone  TEXT,
                status      TEXT DEFAULT 'pending',
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id          SERIAL PRIMARY KEY,
                listing_id  UUID REFERENCES listings(listing_id),
                reporter_id BIGINT,
                created_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_brand_model ON listings(brand, model)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_user ON listings(user_id)")
        await conn.commit()


# ── Users ──────────────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str):
    async with _pool.connection() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username
        """, (user_id, username))
        await conn.commit()


async def save_user_phone(user_id: int, phone: str):
    async with _pool.connection() as conn:
        await conn.execute("UPDATE users SET phone=%s WHERE user_id=%s", (phone, user_id))
        await conn.commit()


async def get_user(user_id: int):
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return await cur.fetchone()


async def count_active_listings(user_id: int) -> int:
    """Counts submitted (pending) + all ever-approved listings.
    Cancelled drafts (deleted, was_approved=FALSE) and rejected = free.
    """
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT COUNT(*) AS cnt FROM listings
                   WHERE user_id=%s AND (status='pending' OR was_approved=TRUE)""",
                (user_id,)
            )
            return (await cur.fetchone())["cnt"]


async def use_paid_slot(user_id: int):
    async with _pool.connection() as conn:
        await conn.execute(
            "UPDATE users SET paid_slots = paid_slots - 1 WHERE user_id=%s AND paid_slots > 0",
            (user_id,)
        )
        await conn.commit()


async def grant_paid_slot(user_id: int):
    async with _pool.connection() as conn:
        await conn.execute(
            "UPDATE users SET paid_slots = paid_slots + 1 WHERE user_id=%s", (user_id,)
        )
        await conn.commit()


# ── Payment requests ───────────────────────────────────────────────────────────

async def create_payment_request(user_id: int, username: str, user_phone: str) -> int:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO payment_requests (user_id, username, user_phone)
                VALUES (%s, %s, %s) RETURNING id
            """, (user_id, username, user_phone))
            row = await cur.fetchone()
            await conn.commit()
            return row["id"]


async def get_payment_request(req_id: int):
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM payment_requests WHERE id=%s", (req_id,))
            return await cur.fetchone()


async def set_payment_request_status(req_id: int, status: str):
    async with _pool.connection() as conn:
        await conn.execute(
            "UPDATE payment_requests SET status=%s WHERE id=%s", (status, req_id)
        )
        await conn.commit()


# ── Listings ───────────────────────────────────────────────────────────────────

async def create_listing(user_id, brand, model, year, mileage, price, currency,
                         city, description, photo_file_ids, phone="", is_paid=False) -> str:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO listings
                    (user_id, brand, model, year, mileage, price, currency, city,
                     description, photo_file_ids, phone, is_paid, status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
                RETURNING listing_id::text
            """, (user_id, brand, model, year, mileage, price, currency,
                  city, description, photo_file_ids, phone, is_paid))
            row = await cur.fetchone()
            await conn.commit()
            return row["listing_id"]


async def get_listing(listing_id: str):
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT *, listing_id::text AS listing_id FROM listings WHERE listing_id=%s::uuid",
                (listing_id,)
            )
            return await cur.fetchone()


async def get_user_listings(user_id: int):
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT * FROM listings
                WHERE user_id=%s AND status != 'deleted'
                ORDER BY created_at DESC
            """, (user_id,))
            return await cur.fetchall()


async def update_listing_fields(listing_id: str, data: dict):
    """Sync FSM state data into the draft listing before publishing."""
    async with _pool.connection() as conn:
        await conn.execute("""
            UPDATE listings SET
                mileage=%s, price=%s, city=%s, description=%s,
                phone=%s, photo_file_ids=%s
            WHERE listing_id=%s::uuid
        """, (
            data.get("mileage"), data.get("price"), data.get("city"),
            data.get("description"), data.get("phone", ""),
            data.get("photos", []), listing_id
        ))
        await conn.commit()


async def approve_listing(listing_id: str):
    """Sets status to active and marks the slot as permanently used."""
    async with _pool.connection() as conn:
        await conn.execute(
            "UPDATE listings SET status='active', was_approved=TRUE WHERE listing_id=%s::uuid",
            (listing_id,)
        )
        await conn.commit()


async def set_listing_status(listing_id: str, status: str):
    async with _pool.connection() as conn:
        await conn.execute(
            "UPDATE listings SET status=%s WHERE listing_id=%s::uuid", (status, listing_id)
        )
        await conn.commit()


async def set_channel_msg(listing_id: str, msg_id: int):
    async with _pool.connection() as conn:
        await conn.execute(
            "UPDATE listings SET channel_msg_id=%s WHERE listing_id=%s::uuid", (msg_id, listing_id)
        )
        await conn.commit()


async def search_listings(brand, model, min_price=None, max_price=None,
                          min_year=None, max_year=None, city=None) -> list:
    conditions = ["status='active'", "brand=%s", "model=%s"]
    params = [brand, model]
    if min_price is not None:
        conditions.append("price >= %s"); params.append(min_price)
    if max_price is not None:
        conditions.append("price <= %s"); params.append(max_price)
    if min_year is not None:
        conditions.append("year >= %s"); params.append(min_year)
    if max_year is not None:
        conditions.append("year <= %s"); params.append(max_year)
    if city:
        conditions.append("city=%s"); params.append(city)
    query = f"SELECT * FROM listings WHERE {' AND '.join(conditions)} ORDER BY is_featured DESC, created_at DESC"
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()


async def get_pending_listings():
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM listings WHERE status='pending' ORDER BY created_at ASC")
            return await cur.fetchall()


async def get_stats():
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS cnt FROM listings WHERE status='active'")
            active = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM users")
            users = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM listings WHERE status='sold'")
            sold = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM listings WHERE status='pending'")
            pending = (await cur.fetchone())["cnt"]
            await cur.execute("SELECT COUNT(*) AS cnt FROM payment_requests WHERE status='pending'")
            pay_req = (await cur.fetchone())["cnt"]
            return {"active": active, "users": users, "sold": sold,
                    "pending": pending, "pay_requests": pay_req}


async def expire_old_listings() -> list:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE listings SET status='expired'
                WHERE status='active' AND was_approved=TRUE AND expires_at < NOW()
                RETURNING user_id, listing_id::text, brand, model
            """)
            rows = await cur.fetchall()
            await conn.commit()
            return rows


async def extend_listing(listing_id: str):
    async with _pool.connection() as conn:
        await conn.execute("""
            UPDATE listings SET status='active', expires_at=NOW() + INTERVAL '30 days'
            WHERE listing_id=%s::uuid
        """, (listing_id,))
        await conn.commit()


async def add_report(listing_id: str, reporter_id: int) -> int:
    async with _pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO reports (listing_id, reporter_id) VALUES (%s::uuid, %s)",
                (listing_id, reporter_id)
            )
            await cur.execute(
                "SELECT COUNT(*) AS cnt FROM reports WHERE listing_id=%s::uuid", (listing_id,)
            )
            count = (await cur.fetchone())["cnt"]
            await conn.commit()
            return count
