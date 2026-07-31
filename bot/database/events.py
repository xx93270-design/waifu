
from __future__ import annotations

import asyncpg
from .db import get_pool


async def create_event(
    name: str,
    event_type: str,
    target_group_id: int | None,
    trigger_messages: int,
    description: str,
    started_by: int,
    multiplier: float = 1.0,
    ends_at=None,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO events
                (name, event_type, target_group_id, trigger_messages, multiplier,
                 description, started_by, ends_at, is_active)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,0)
            RETURNING id
            """,
            name, event_type, target_group_id, trigger_messages, multiplier,
            description, started_by, ends_at
        )
        return int(row["id"])


async def get_event(event_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM events WHERE id=$1", event_id)
        return dict(row) if row else None


async def list_events(group_id: int | None = None, active_only: bool | None = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        where = []
        params = []
        if group_id is not None:
            params.append(group_id)
            where.append(f"target_group_id=${len(params)}")
        if active_only is True:
            where.append("is_active=1")
        elif active_only is False:
            where.append("is_active=0")
        q = "SELECT * FROM events"
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY started_at DESC, id DESC"
        rows = await conn.fetch(q, *params)
        return [dict(r) for r in rows]


async def get_active_event_for_group(group_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM events
            WHERE is_active=1
              AND (target_group_id IS NULL OR target_group_id=$1)
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """,
            group_id,
        )
        return dict(row) if row else None


async def toggle_event(event_id: int, enabled: bool):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE events SET is_active=$1, updated_at=NOW() WHERE id=$2",
            1 if enabled else 0,
            event_id,
        )


async def update_event_field(event_id: int, field: str, value):
    allowed = {
        "name": "name",
        "event_type": "event_type",
        "target_group_id": "target_group_id",
        "trigger_messages": "trigger_messages",
        "multiplier": "multiplier",
        "description": "description",
        "ends_at": "ends_at",
    }
    column = allowed.get(field)
    if not column:
        raise ValueError("Unsupported field")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE events SET {column}=$1, updated_at=NOW() WHERE id=$2",
            value,
            event_id,
        )


async def delete_event(event_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM event_waifus WHERE event_id=$1", event_id)
        await conn.execute("DELETE FROM events WHERE id=$1", event_id)


async def add_event_waifu(event_id: int, waifu_id: str, price: int = 0, weight: int = 100):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO event_waifus (event_id, waifu_id, price, weight, is_active)
            VALUES ($1,$2,$3,$4,1)
            ON CONFLICT (event_id, waifu_id)
            DO UPDATE SET price=$3, weight=$4, is_active=1
            """,
            event_id, waifu_id, price, weight,
        )


async def remove_event_waifu(event_id: int, waifu_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM event_waifus WHERE event_id=$1 AND waifu_id=$2",
            event_id,
            waifu_id,
        )


async def get_event_waifus(event_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ew.*, w.name, w.anime, w.rarity, w.file_id, w.price AS base_price
            FROM event_waifus ew
            JOIN waifus w ON ew.waifu_id=w.waifu_id
            WHERE ew.event_id=$1 AND ew.is_active=1 AND w.is_active=1
            ORDER BY ew.id ASC
            """,
            event_id,
        )
        return [dict(r) for r in rows]


async def pick_event_waifu(event_id: int):
    items = await get_event_waifus(event_id)
    if not items:
        return None
    # weight-based pick
    weights = [max(1, int(i.get("weight") or 1)) for i in items]
    import random
    item = random.choices(items, weights=weights, k=1)[0]
    return item
