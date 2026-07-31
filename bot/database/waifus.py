
from __future__ import annotations

import random
from .db import get_pool
from utils.helpers import pick_random_rarity, normalize_rarity


async def add_waifu(
    name: str,
    anime: str,
    rarity: str,
    file_id: str,
    added_by: int,
    price: int = 0,
    group_id: int | None = None,
    event_id: int | None = None,
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO waifus (waifu_id, name, anime, rarity, file_id, price, group_id, event_id, added_by)
                VALUES ('__tmp__', $1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                name,
                anime,
                normalize_rarity(rarity),
                file_id,
                int(price or 0),
                group_id,
                event_id,
                added_by,
            )
            new_id = row['id']
            waifu_id = str(new_id)
            await conn.execute("UPDATE waifus SET waifu_id=$1 WHERE id=$2", waifu_id, new_id)
            return True, waifu_id
        except Exception as e:
            print("add_waifu error:", e)
            return False, ""


async def get_waifu(waifu_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM waifus WHERE waifu_id=$1 AND is_active=1",
            waifu_id,
        )
        return dict(row) if row else None


async def get_waifu_by_db_id(db_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM waifus WHERE id=$1 AND is_active=1", db_id)
        return dict(row) if row else None


async def get_random_waifu(rarity: str = None, group_id: int | None = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = ["is_active=1"]
        params = []
        if rarity:
            params.append(normalize_rarity(rarity))
            conditions.append(f"rarity=${len(params)}")
        if group_id is not None:
            params.append(group_id)
            conditions.append(f"group_id=${len(params)}")
        where = " AND ".join(conditions)
        row = await conn.fetchrow(
            f"SELECT * FROM waifus WHERE {where} ORDER BY RANDOM() LIMIT 1",
            *params,
        )
        return dict(row) if row else None


async def get_random_waifu_by_rarity_weight(group_id: int | None = None):
    rarity = pick_random_rarity()
    waifu = await get_random_waifu(rarity, group_id=group_id)
    if not waifu and group_id is not None:
        waifu = await get_random_waifu(rarity, group_id=None)
    if not waifu:
        waifu = await get_random_waifu(None, group_id=group_id)
    if not waifu:
        waifu = await get_random_waifu()
    return waifu


async def remove_waifu(waifu_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE waifus SET is_active=0 WHERE waifu_id=$1", waifu_id)


async def remove_waifu_by_db_id(db_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE waifus SET is_active=0 WHERE id=$1", db_id)


async def update_waifu_field(db_id: int, field: str, value):
    allowed = {
        "name": "name",
        "anime": "anime",
        "rarity": "rarity",
        "file_id": "file_id",
        "price": "price",
        "group_id": "group_id",
        "event_id": "event_id",
        "is_active": "is_active",
    }
    column = allowed.get(field)
    if not column:
        raise ValueError(f"Unsupported field: {field}")

    pool = await get_pool()
    async with pool.acquire() as conn:
        if column in {"price", "group_id", "event_id", "is_active"} and value is not None:
            try:
                value = int(value)
            except Exception:
                pass
        if column == "rarity" and value is not None:
            value = normalize_rarity(str(value))
        await conn.execute(f"UPDATE waifus SET {column}=$1 WHERE id=$2", value, db_id)


async def get_all_waifus_paginated(limit: int = 8, offset: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM waifus WHERE is_active=1 ORDER BY id ASC LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
        return [dict(r) for r in rows]


async def get_waifus_by_admin(added_by: int, limit: int = 8, offset: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM waifus WHERE is_active=1 AND added_by=$1 ORDER BY id ASC LIMIT $2 OFFSET $3",
            added_by,
            limit,
            offset,
        )
        return [dict(r) for r in rows]


async def count_waifus_by_admin(added_by: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM waifus WHERE is_active=1 AND added_by=$1", added_by) or 0


async def count_all_active() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM waifus WHERE is_active=1") or 0


async def search_waifus(query: str, limit: int = 10):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM waifus WHERE is_active=1 AND (name ILIKE $1 OR anime ILIKE $1) LIMIT $2",
            "%" + query + "%",
            limit,
        )
        return [dict(r) for r in rows]


async def get_waifus_by_anime(anime: str, limit: int = 20):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM waifus WHERE is_active=1 AND anime ILIKE $1 LIMIT $2",
            "%" + anime + "%",
            limit,
        )
        return [dict(r) for r in rows]


async def count_waifus_by_rarity():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT rarity, COUNT(*) as cnt FROM waifus WHERE is_active=1 GROUP BY rarity"
        )
        return {r['rarity']: r['cnt'] for r in rows}


async def count_all_waifus() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM waifus WHERE is_active=1") or 0


async def get_all_waifus(limit: int = 50, offset: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM waifus WHERE is_active=1 ORDER BY id ASC LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
        return [dict(r) for r in rows]


async def get_waifus_by_group(group_id: int, limit: int = 50, offset: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM waifus WHERE is_active=1 AND group_id=$1 ORDER BY rarity, id ASC LIMIT $2 OFFSET $3",
            group_id,
            limit,
            offset,
        )
        return [dict(r) for r in rows]


async def count_waifus_by_group(group_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM waifus WHERE is_active=1 AND group_id=$1", group_id) or 0
