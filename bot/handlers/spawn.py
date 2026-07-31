
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import waifus as waifu_db
from database import collections as col_db
from database import users as user_db
from database import groups as grp_db
from database import logs as log_db
from database import events as event_db
from database import settings as settings_db
from utils.helpers import get_rarity_emoji, get_coin_reward, mention_user, normalize_rarity, pick_random_rarity
from utils.stickers import get_catch_sticker, send_sticker as send_stk

SPAWN_TIMEOUT = 15 * 60  # 15 daqiqa

active_spawns: dict[int, dict] = {}

_catch_attempts: dict[int, list[float]] = {}
CATCH_LIMIT = 3
CATCH_WINDOW = 60


def _is_catch_flooded(user_id: int) -> bool:
    now = time.time()
    attempts = _catch_attempts.get(user_id, [])
    attempts = [t for t in attempts if now - t < CATCH_WINDOW]
    if len(attempts) >= CATCH_LIMIT:
        _catch_attempts[user_id] = attempts
        return True
    attempts.append(now)
    _catch_attempts[user_id] = attempts
    return False


async def _roll_rarity_with_divine() -> str:
    """
    Base rarity roll uses screenshot probabilities.
    Divine appears only every 10th Exclusive roll.
    """
    rarity = normalize_rarity(pick_random_rarity())
    if rarity == "Exclusive":
        counter = await settings_db.bump_exclusive_counter()
        if counter >= 10:
            await settings_db.reset_exclusive_counter()
            return "Divine"
    return rarity


async def _pick_group_waifu(group_id: int, rarity: str):
    waifu = await waifu_db.get_random_waifu(rarity=rarity, group_id=group_id)
    if not waifu and rarity == "Divine":
        waifu = await waifu_db.get_random_waifu(rarity="Exclusive", group_id=group_id)
    if not waifu:
        waifu = await waifu_db.get_random_waifu(rarity=rarity)
    if not waifu and rarity == "Divine":
        waifu = await waifu_db.get_random_waifu(rarity="Exclusive")
    if not waifu:
        waifu = await waifu_db.get_random_waifu(group_id=group_id)
    if not waifu:
        waifu = await waifu_db.get_random_waifu()
    return waifu


async def _pick_event_or_global_spawn(group_id: int):
    active_event = await event_db.get_active_event_for_group(group_id)
    if active_event:
        item = await event_db.pick_event_waifu(active_event["id"])
        if item:
            waifu = {
                "id": None,
                "waifu_id": item["waifu_id"],
                "name": item["name"],
                "anime": item["anime"],
                "rarity": normalize_rarity(item["rarity"]),
                "file_id": item["file_id"],
                "price": int(item.get("price") or item.get("base_price") or 0),
                "group_id": None,
            }
            return waifu, "event", active_event
    rarity = await _roll_rarity_with_divine()
    waifu = await _pick_group_waifu(group_id, rarity)
    if not waifu:
        return None, None, None
    return waifu, "global", None


async def restore_active_spawns(context):
    """Restartdan keyin DB dagi aktiv spawnlarni xotiraga qayta yuklaydi."""
    now = datetime.now()
    restored = 0
    try:
        pool = await grp_db.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM spawn_state WHERE waifu_id IS NOT NULL")
            expired_ids = []
            for row in rows:
                group_id = row["group_id"]
                waifu_id = row["waifu_id"]
                expires_at = row["expires_at"]
                if not expires_at:
                    expired_ids.append(group_id)
                    continue
                if expires_at.replace(tzinfo=None) <= now:
                    expired_ids.append(group_id)
                    continue
                waifu = await waifu_db.get_waifu(waifu_id)
                if not waifu:
                    expired_ids.append(group_id)
                    continue

                row_dict = dict(row)
                active_spawns[group_id] = {
                    "waifu_id": waifu["waifu_id"],
                    "waifu_name": waifu["name"],
                    "file_id": waifu["file_id"],
                    "rarity": normalize_rarity(waifu["rarity"]),
                    "anime": waifu["anime"],
                    "expires_at": expires_at.replace(tzinfo=None),
                    "coin_multiplier": 1.0,
                    "reward": int(row_dict.get("reward") or waifu.get("price") or get_coin_reward(waifu["rarity"])),
                    "source_type": row_dict.get("source_type") or "global",
                    "event_id": row_dict.get("event_id"),
                }
                remaining = (expires_at.replace(tzinfo=None) - now).total_seconds()
                asyncio.create_task(expire_spawn(context, group_id, int(remaining)))
                restored += 1

            for gid in expired_ids:
                await conn.execute("DELETE FROM spawn_state WHERE group_id=$1", gid)
    except Exception as e:
        print("restore_active_spawns error:", e)
    if restored:
        print("Restored", restored, "active spawn(s) from DB")


async def handle_message_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return
    group_id = chat.id
    user = update.effective_user
    if not user or user.is_bot:
        return

    await user_db.get_or_create_user(user.id, user.username, user.full_name)

    try:
        bot_member = await context.bot.get_chat_member(group_id, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            return
    except Exception:
        return

    from middlewares.flood import check_flood
    is_flooded = await check_flood(user.id, group_id, context)
    if is_flooded:
        return

    active_event = await event_db.get_active_event_for_group(group_id)
    threshold = int(active_event["trigger_messages"]) if active_event else await grp_db.get_spawn_threshold(group_id)

    count = await grp_db.increment_message_count(group_id)
    if count < threshold:
        return

    await grp_db.reset_message_count(group_id)
    if group_id in active_spawns:
        return

    await do_spawn(context, group_id, chat.title)


async def do_spawn(context: ContextTypes.DEFAULT_TYPE, group_id: int, group_name: str = None):
    waifu, source_type, active_event = await _pick_event_or_global_spawn(group_id)
    if not waifu:
        return

    multiplier = await log_db.get_event_multiplier()
    spawned_at = datetime.now()
    expires_at = spawned_at + timedelta(seconds=SPAWN_TIMEOUT)

    reward = int(waifu.get("price") or get_coin_reward(waifu["rarity"]))
    reward = int(reward * multiplier)

    active_spawns[group_id] = {
        "waifu_id": waifu["waifu_id"],
        "waifu_name": waifu["name"],
        "file_id": waifu["file_id"],
        "rarity": normalize_rarity(waifu["rarity"]),
        "anime": waifu["anime"],
        "expires_at": expires_at,
        "coin_multiplier": multiplier,
        "reward": reward,
        "source_type": source_type,
        "event_id": active_event["id"] if active_event else None,
        "event_name": active_event["name"] if active_event else None,
    }

    await grp_db.set_spawn_state(
        group_id,
        waifu["waifu_id"],
        spawned_at,
        expires_at,
        source_type=source_type,
        event_id=active_event["id"] if active_event else None,
        reward=reward,
    )

    emoji = get_rarity_emoji(waifu["rarity"])
    source_tag = ""
    if source_type == "event" and active_event:
        source_tag = f"\n⚡ Event: <b>{active_event['name']}</b>"
    event_mark = " ⚡x" + str(multiplier) if multiplier > 1 else ""

    caption = (
        "✨ <b>Yangi waifu paydo bo'ldi!</b>" + event_mark + "\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        + emoji + " <b>" + normalize_rarity(waifu["rarity"]) + "</b> • 🎌 " + waifu["anime"] + "\n"
        + source_tag + "\n"
        "💰 Narx: <b>" + f"{reward:,}" + "</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 Tutish: <code>/waifu [ism]</code>\n"
        f"⏳ Vaqt: <b>{SPAWN_TIMEOUT // 60} daqiqa</b>"
    )

    await log_db.add_log(
        "spawn",
        details=f"waifu_id={waifu['waifu_id']} rarity={waifu['rarity']} source={source_type}",
        group_id=group_id,
    )

    try:
        await context.bot.send_photo(chat_id=group_id, photo=waifu["file_id"], caption=caption, parse_mode="HTML")
    except Exception as e:
        print("Spawn error in", group_id, ":", e)
        active_spawns.pop(group_id, None)
        return

    asyncio.create_task(expire_spawn(context, group_id, SPAWN_TIMEOUT))


async def expire_spawn(context: ContextTypes.DEFAULT_TYPE, group_id: int, timeout: int):
    await asyncio.sleep(timeout)
    if group_id in active_spawns:
        waifu_name = active_spawns[group_id]["waifu_name"]
        active_spawns.pop(group_id, None)
        await grp_db.clear_spawn_state(group_id)
        try:
            await context.bot.send_message(
                chat_id=group_id,
                text="⌛ Vaqt tugadi! <b>" + waifu_name + "</b> yo'qoldi. 😢",
                parse_mode="HTML",
            )
        except Exception:
            pass


def _name_matches(guess: str, correct: str) -> bool:
    guess = guess.lower().strip()
    correct = correct.lower().strip()
    if not guess:
        return False
    if guess == correct:
        return True
    if correct.startswith(guess) and len(guess) >= 2:
        return True
    if guess in correct and len(guess) >= 3:
        return True
    name_words = [w for w in correct.split() if len(w) >= 2]
    guess_words = guess.split()
    for gw in guess_words:
        if len(gw) >= 2 and any(gw == nw or nw.startswith(gw) for nw in name_words):
            return True
    return False


async def cmd_waifu_catch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("⚠️ Bu buyruq faqat guruhlarda ishlaydi.")
        return

    group_id = chat.id
    user = update.effective_user

    from middlewares.flood import is_flood_banned, flood_ban_remaining
    if is_flood_banned(user.id, group_id):
        remaining = flood_ban_remaining(user.id, group_id)
        m = remaining // 60
        s = remaining % 60
        await update.message.reply_text(
            "⚠️ Flood uchun cheklangan.\nKutish: <b>" + str(m) + ":" + str(s).zfill(2) + "</b>",
            parse_mode="HTML",
        )
        return

    if group_id not in active_spawns:
        await update.message.reply_text("⚠️ Hozirda hech qanday waifu paydo bo'lmagan.")
        return

    if not context.args:
        spawn = active_spawns.get(group_id, {})
        emoji = get_rarity_emoji(spawn.get("rarity", "Common"))
        await update.message.reply_text(
            "❓ Format: <code>/waifu [ism]</code>\nMisol: <code>/waifu Mikasa</code>\n\n"
            + emoji
            + " Rarity: <b>"
            + spawn.get("rarity", "?")
            + "</b> | Anime: "
            + spawn.get("anime", "?"),
            parse_mode="HTML",
        )
        return

    spawn = active_spawns[group_id]
    if datetime.now() > spawn["expires_at"]:
        active_spawns.pop(group_id, None)
        await update.message.reply_text("⌛ Bu waifu allaqachon yo'qolgan!")
        return

    if _is_catch_flooded(user.id):
        await update.message.reply_text(
            "⏳ Juda tez! "
            + str(CATCH_WINDOW)
            + "s ichida "
            + str(CATCH_LIMIT)
            + " ta urinish."
        )
        return

    guess = " ".join(context.args)
    if not _name_matches(guess, spawn["waifu_name"]):
        await update.message.reply_text("❌ Noto'g'ri! Yana urinib ko'ring 🤔")
        return

    caught_spawn = active_spawns.pop(group_id, None)
    if not caught_spawn:
        return

    await grp_db.clear_spawn_state(group_id)

    waifu = await waifu_db.get_waifu(spawn["waifu_id"])
    if not waifu:
        return

    await user_db.get_or_create_user(user.id, user.username, user.full_name)
    coin_reward = int(spawn.get("reward") or waifu.get("price") or get_coin_reward(spawn["rarity"]))
    await col_db.add_to_collection(user.id, spawn["waifu_id"])
    await user_db.add_coins(user.id, coin_reward)
    await user_db.update_total_caught(user.id)

    emoji = get_rarity_emoji(spawn["rarity"])
    event_bonus = " ⚡" if spawn.get("coin_multiplier", 1.0) > 1 else ""
    await log_db.add_log(
        "catch",
        user_id=user.id,
        details="waifu_id=" + spawn["waifu_id"] + " rarity=" + spawn["rarity"],
        group_id=group_id,
    )

    await update.message.reply_text(
        "🎉 "
        + mention_user(user.id, user.full_name or user.username or "Noma'lum")
        + " waifuni qo'lga kiritdi!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        + emoji
        + " <b>"
        + waifu["name"]
        + "</b>\n"
        "🎌 "
        + waifu["anime"]
        + " • ⭐ "
        + waifu["rarity"]
        + "\n"
        "🆔 <code>#"
        + waifu["waifu_id"]
        + "</code>\n"
        "💰 +"
        + f"{coin_reward:,}"
        + " coin"
        + event_bonus
        + "\n"
        "━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

    stk = get_catch_sticker(spawn["rarity"])
    await send_stk(context.bot, group_id, stk)
