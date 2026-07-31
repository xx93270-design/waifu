
import os
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Screenshotdagi tartibga mos yangi raritylar
RARITY_CONFIG = {
    "Common": {"weight": 800000, "emoji": "⚪", "coin_reward": 10, "color": "white"},
    "Rare": {"weight": 100000, "emoji": "🟢", "coin_reward": 25, "color": "green"},
    "Super Rare": {"weight": 50000, "emoji": "🔵", "coin_reward": 50, "color": "blue"},
    "Epic": {"weight": 30000, "emoji": "🟣", "coin_reward": 100, "color": "purple"},
    "Mythic": {"weight": 10000, "emoji": "🟠", "coin_reward": 200, "color": "orange"},
    "Legendary": {"weight": 9000, "emoji": "🟡", "coin_reward": 500, "color": "gold"},
    "Premium": {"weight": 990, "emoji": "💎", "coin_reward": 1000, "color": "cyan"},
    "Exclusive": {"weight": 10, "emoji": "👑", "coin_reward": 5000, "color": "rainbow"},
    "Divine": {"weight": 0, "emoji": "✨", "coin_reward": 25000, "color": "white"},
}

# Divine alohida shart bilan keladi
RARITY_ORDER = [
    "Common",
    "Rare",
    "Super Rare",
    "Epic",
    "Mythic",
    "Legendary",
    "Premium",
    "Exclusive",
    "Divine",
]

BASE_RARITY_ORDER = [r for r in RARITY_ORDER if r != "Divine"]


def normalize_rarity(rarity: str) -> str:
    if not rarity:
        return "Common"
    x = str(rarity).strip().lower().replace("_", " ")
    aliases = {
        "common": "Common",
        "rare": "Rare",
        "super rare": "Super Rare",
        "superrare": "Super Rare",
        "epic": "Epic",
        "mythic": "Mythic",
        "legendary": "Legendary",
        "premium": "Premium",
        "exclusive": "Exclusive",
        "divine": "Divine",
    }
    return aliases.get(x, rarity.strip().title())


def get_rarity_emoji(rarity: str) -> str:
    return RARITY_CONFIG.get(normalize_rarity(rarity), {}).get("emoji", "❓")


def get_coin_reward(rarity: str) -> int:
    return RARITY_CONFIG.get(normalize_rarity(rarity), {}).get("coin_reward", 10)


def pick_random_rarity() -> str:
    rarities = BASE_RARITY_ORDER
    weights = [RARITY_CONFIG[r]["weight"] for r in rarities]
    return random.choices(rarities, weights=weights, k=1)[0]


def format_profile(user: dict, collection_count: int, rank: int, title: str = None) -> str:
    full_name = user['full_name'] or "Noma'lum"
    title_line = f"🏅 Unvon: <b>{title}</b>\n" if title else ""
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>PROFIL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"👤 Ism: <b>{full_name}</b>\n"
        f"{title_line}"
        f"💰 Coin: <b>{user['coins']:,}</b>\n"
        f"🎴 Kolleksiya: <b>{collection_count}</b> ta\n"
        f"🏆 Topilgan: <b>{user['total_caught']}</b> ta\n"
        f"🔄 Trade: <b>{user['trade_count']}</b> ta\n"
        f"📊 Reyting: <b>#{rank}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def format_waifu_card(waifu: dict, collection_id: int = None) -> str:
    emoji = get_rarity_emoji(waifu['rarity'])
    lines = [
        f"━━━━━━━━━━━━━━━━━━━━",
        f"{emoji} <b>{normalize_rarity(waifu['rarity']).upper()}</b> {emoji}",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"📛 Ism: <b>{waifu['name']}</b>",
        f"🎌 Anime: <b>{waifu['anime']}</b>",
        f"🆔 ID: <code>{waifu['waifu_id']}</code>",
        f"💰 Narx: <b>{int(waifu.get('price') or 0):,}</b>",
    ]
    if waifu.get('group_id') is not None:
        lines.append(f"👥 Guruh: <code>{waifu['group_id']}</code>")
    if collection_id:
        lines.append(f"🗂 Kolleksiya ID: <code>{collection_id}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def generate_waifu_id(rarity: str) -> str:
    prefix_map = {
        "Common": "CM", "Rare": "RR", "Super Rare": "SR",
        "Epic": "EP", "Mythic": "MY", "Legendary": "LG",
        "Premium": "PR", "Exclusive": "EX", "Divine": "DV"
    }
    prefix = prefix_map.get(normalize_rarity(rarity), "WF")
    number = random.randint(100000, 999999)
    return f"{prefix}-{number}"


def is_god_admin(user_id: int) -> bool:
    god_id = os.environ.get("GOD_ADMIN_ID", "")
    try:
        return int(god_id) == int(user_id)
    except Exception:
        return False


def mention_user(user_id: int, full_name: str) -> str:
    display_name = full_name or "Noma'lum"
    return f'<a href="tg://user?id={user_id}">{display_name}</a>'


def safe_int(value, default=None):
    try:
        return int(value)
    except Exception:
        return default


def now_naive():
    return datetime.now()
