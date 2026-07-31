
from __future__ import annotations

from .db import get_pool


async def get_setting(key: str, default=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT value FROM bot_settings WHERE key=$1", key)
        return default if val is None else val


async def set_setting(key: str, value):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value=$2
            """,
            key,
            str(value),
        )


async def get_int_setting(key: str, default: int = 0) -> int:
    raw = await get_setting(key, None)
    try:
        return int(raw)
    except Exception:
        return default


async def set_int_setting(key: str, value: int):
    await set_setting(key, int(value))


async def get_private_group_id() -> int | None:
    val = await get_int_setting("private_group_id", 0)
    return val or None


async def set_private_group_id(group_id: int):
    await set_int_setting("private_group_id", group_id)


async def get_private_channel_id() -> int | None:
    val = await get_int_setting("private_channel_id", 0)
    return val or None


async def set_private_channel_id(channel_id: int):
    await set_int_setting("private_channel_id", channel_id)


async def get_exclusive_counter() -> int:
    return await get_int_setting("exclusive_counter", 0)


async def set_exclusive_counter(value: int):
    await set_int_setting("exclusive_counter", value)


async def bump_exclusive_counter() -> int:
    value = await get_exclusive_counter()
    value += 1
    await set_exclusive_counter(value)
    return value


async def reset_exclusive_counter():
    await set_exclusive_counter(0)
