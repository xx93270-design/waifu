
from __future__ import annotations

import asyncio
import shlex
from datetime import datetime
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import ContextTypes

from database import waifus as waifu_db
from database import users as user_db
from database import logs as log_db
from database import groups as grp_db
from database import collections as col_db
from database import titles as title_db
from database import events as event_db
from database import settings as settings_db
from database.db import get_pool
from utils.helpers import (
    get_rarity_emoji,
    is_god_admin,
    RARITY_ORDER,
    normalize_rarity,
    format_waifu_card,
)

# ──────────────────────────────────────
#  PANEL TUGMALARI
# ──────────────────────────────────────
BTN_ADDWAIFU = "➕ Waifu qo'shish"
BTN_WAIFUS = "🎴 Waifular"
BTN_EDITWAIFU = "✏️ Waifu tahrir"
BTN_GROUPS = "👥 Guruhlar"
BTN_EVENTS = "⚡ Eventlar"
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_USERS = "👤 A'zolar"
BTN_ADDADMIN = "👑 Admin qo'shish"
BTN_RMADMIN = "🔴 Admin o'chirish"
BTN_BROADCAST = "📣 Broadcast"
BTN_STATS = "📊 Statistika"
BTN_CLOSE = "🚪 Panelni yopish"

SUB_ADMIN_BUTTONS = {BTN_ADDWAIFU, BTN_WAIFUS, BTN_CLOSE}

ALL_PANEL_BUTTONS = {
    BTN_ADDWAIFU,
    BTN_WAIFUS,
    BTN_EDITWAIFU,
    BTN_GROUPS,
    BTN_EVENTS,
    BTN_SETTINGS,
    BTN_USERS,
    BTN_ADDADMIN,
    BTN_RMADMIN,
    BTN_BROADCAST,
    BTN_STATS,
    BTN_CLOSE,
}

ADM_STATE = "adm_state"
ADM_DATA = "adm_data"

S_NONE = None
S_PHOTO = "addwaifu_photo"
S_NAME = "addwaifu_name"
S_ANIME = "addwaifu_anime"
S_RARITY = "addwaifu_rarity"
S_PRICE = "addwaifu_price"
S_GROUP = "addwaifu_group"

PAGE_SIZE = 8


def _panel_kb(role: str) -> ReplyKeyboardMarkup:
    if role == "sub":
        rows = [
            [BTN_ADDWAIFU, BTN_WAIFUS],
            [BTN_CLOSE],
        ]
    elif role == "god":
        rows = [
            [BTN_ADDWAIFU, BTN_WAIFUS, BTN_EDITWAIFU],
            [BTN_GROUPS, BTN_EVENTS, BTN_SETTINGS],
            [BTN_USERS, BTN_STATS],
            [BTN_ADDADMIN, BTN_RMADMIN],
            [BTN_BROADCAST],
            [BTN_CLOSE],
        ]
    else:
        rows = [
            [BTN_ADDWAIFU, BTN_WAIFUS, BTN_EDITWAIFU],
            [BTN_GROUPS, BTN_EVENTS, BTN_SETTINGS],
            [BTN_USERS, BTN_STATS],
            [BTN_BROADCAST],
            [BTN_CLOSE],
        ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


def _clear_state(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(ADM_STATE, None)
    context.user_data.pop(ADM_DATA, None)


def _set_state(context: ContextTypes.DEFAULT_TYPE, state: str, data: Optional[dict] = None):
    context.user_data[ADM_STATE] = state
    if data is not None:
        context.user_data[ADM_DATA] = data


async def _get_role(user_id: int) -> str:
    role = await log_db.get_admin_role(user_id)
    return role or ""


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user or not await log_db.is_admin(user.id):
        if update.message:
            await update.message.reply_text("❌ Ruxsatingiz yo'q.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Ruxsatingiz yo'q.", show_alert=True)
        return False
    return True


async def require_full_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user or not await log_db.is_full_admin(user.id):
        if update.message:
            await update.message.reply_text("❌ Bu amal faqat to'liq admin uchun.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Bu amal faqat to'liq admin uchun.", show_alert=True)
        return False
    return True


async def require_god(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user or not is_god_admin(user.id):
        if update.message:
            await update.message.reply_text("❌ Bu faqat God Admin uchun.")
        elif update.callback_query:
            await update.callback_query.answer("❌ Bu faqat God Admin uchun.", show_alert=True)
        return False
    return True


def _parse_cmd_text(text: str) -> list[str]:
    if not text:
        return []
    body = text.split(maxsplit=1)
    if len(body) < 2:
        return []
    try:
        return shlex.split(body[1])
    except Exception:
        return body[1].split()


def _usage_for_waifu_edit() -> str:
    return (
        "✏️ <b>Waifu tahrir</b>\n"
        "Format: <code>/waifuedit ID field value</code>\n"
        "Maydonlar: name, anime, rarity, file_id, price, group_id, event_id, is_active\n"
        "Misol: <code>/waifuedit 12 rarity Divine</code>\n"
        "Misol: <code>/waifuedit 12 price 5000</code>"
    )


async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    _clear_state(context)
    role = await _get_role(update.effective_user.id)
    role_label = {"god": "👑 God Admin", "admin": "🔧 Admin", "sub": "🟡 Sub-Admin"}.get(role, "Admin")
    await update.message.reply_text(
        f"🛡️ <b>ADMIN PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Salom, <b>{role_label}</b>!\n"
        f"Kerakli bo'limni tanlang 👇",
        parse_mode="HTML",
        reply_markup=_panel_kb(role),
    )


# ──────────────────────────────────────
#  WAIFU RO'YXATI / INFO / EDIT
# ──────────────────────────────────────

async def _show_waifu_list(message, page: int = 0, edit: bool = False, owner_id: int = None):
    if owner_id:
        total = await waifu_db.count_waifus_by_admin(owner_id)
        items = await waifu_db.get_waifus_by_admin(owner_id, limit=PAGE_SIZE, offset=page * PAGE_SIZE)
    else:
        total = await waifu_db.count_all_active()
        items = await waifu_db.get_all_waifus_paginated(limit=PAGE_SIZE, offset=page * PAGE_SIZE)

    if total == 0:
        text = "📦 Hali waifu qo'shilmagan." if owner_id else "📦 Bazada hali waifu yo'q."
        if edit:
            try:
                await message.edit_text(text)
            except Exception:
                pass
        else:
            await message.reply_text(text)
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    scope = "Mening waifularim" if owner_id else "Jami waifular"
    lines = [
        f"🎴 <b>{scope}</b> — {total} ta\n📄 Sahifa {page+1}/{total_pages}\n━━━━━━━━━━━━━━━━━━━━"
    ]
    for w in items:
        emoji = get_rarity_emoji(w["rarity"])
        grp = f" | <code>{w['group_id']}</code>" if w.get("group_id") is not None else ""
        lines.append(f"<b>#{w['id']}</b> {emoji} {w['name']} — <i>{w['anime']}</i> [{w['rarity']}]{grp}")
    lines.append("━━━━━━━━━━━━━━━━━━━━\n🗑 O'chirish uchun tugmani bosing:")

    del_buttons = []
    row = []
    for w in items:
        row.append(InlineKeyboardButton(f"🗑#{w['id']} {w['name'][:9]}", callback_data=f"adm_wdel_{w['id']}"))
        if len(row) == 2:
            del_buttons.append(row)
            row = []
    if row:
        del_buttons.append(row)

    nav = []
    page_key = f"adm_wlist_sub_{page}" if owner_id else f"adm_wlist_{page}"
    prev_key = f"adm_wlist_sub_{page-1}" if owner_id else f"adm_wlist_{page-1}"
    next_key = f"adm_wlist_sub_{page+1}" if owner_id else f"adm_wlist_{page+1}"
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=prev_key))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="adm_noop"))
    if (page + 1) < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=next_key))
    del_buttons.append(nav)

    keyboard = InlineKeyboardMarkup(del_buttons)
    text = "\n".join(lines)
    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            pass
    else:
        await message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _show_users(message):
    all_ids = await user_db.get_all_users()
    top = await user_db.get_top_users(limit=10, by="total_caught")
    lines = [
        "👥 <b>FOYDALANUVCHILAR</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Jami foydalanuvchilar: <b>{len(all_ids)}</b>",
        "🏆 Top catch:",
    ]
    for i, u in enumerate(top, 1):
        name = u.get("full_name") or u.get("username") or str(u["user_id"])
        lines.append(f"{i}. <code>{u['user_id']}</code> — {name} ({u.get('total_caught', 0)})")
    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def _show_stats(message):
    waifu_count = await waifu_db.count_all_active()
    group_count = len(await grp_db.get_all_groups())
    event_count = len(await event_db.list_events())
    admin_count = len(await log_db.get_admins())
    active_event = await event_db.get_active_event_for_group((await settings_db.get_private_group_id()) or 0)
    lines = [
        "📊 <b>STATISTIKA</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🎴 Waifular: <b>{waifu_count}</b>",
        f"👥 Guruhlar: <b>{group_count}</b>",
        f"⚡ Eventlar: <b>{event_count}</b>",
        f"🛡 Adminlar: <b>{admin_count}</b>",
    ]
    if active_event:
        lines.append(f"✅ Faol event: <b>{active_event['name']}</b>")
    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_waifuinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /waifuinfo [id]")
        return
    raw = context.args[0].lstrip("#")
    try:
        db_id = int(raw)
    except ValueError:
        await update.message.reply_text("❌ ID raqam bo'lishi kerak.")
        return
    waifu = await waifu_db.get_waifu_by_db_id(db_id)
    if not waifu:
        await update.message.reply_text("❌ Waifu topilmadi.")
        return
    await update.message.reply_text(format_waifu_card(waifu), parse_mode="HTML")


async def cmd_waifuedit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    args = _parse_cmd_text(update.message.text)
    if len(args) < 3:
        await update.message.reply_text(_usage_for_waifu_edit(), parse_mode="HTML")
        return
    try:
        db_id = int(args[0].lstrip("#"))
    except ValueError:
        await update.message.reply_text("❌ ID noto'g'ri.")
        return
    field = args[1].strip().lower()
    value = " ".join(args[2:]).strip()
    try:
        if field in {"price", "group_id", "event_id", "is_active"}:
            value = int(value)
        if field == "rarity":
            value = normalize_rarity(value)
        await waifu_db.update_waifu_field(db_id, field, value)
    except Exception as e:
        await update.message.reply_text(f"❌ Tahrirlash xatosi: {e}")
        return
    waifu = await waifu_db.get_waifu_by_db_id(db_id)
    await update.message.reply_text(
        f"✅ Tahrirlandi.\n\n{format_waifu_card(waifu)}",
        parse_mode="HTML",
    )


# ──────────────────────────────────────
#  WAIFU QO'SHISH FLOW
# ──────────────────────────────────────

async def cmd_addwaifu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    _set_state(context, S_PHOTO, {})
    await update.message.reply_text(
        "📸 Waifu rasmini yuboring.\n"
        "Keyin ism, anime, rarity, narx va group ID so'raladi."
    )


async def handle_admin_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    if not await require_admin(update, context):
        return
    state = context.user_data.get(ADM_STATE)
    if state != S_PHOTO:
        return
    data = context.user_data.get(ADM_DATA, {})
    data["file_id"] = update.message.photo[-1].file_id
    _set_state(context, S_NAME, data)
    await update.message.reply_text("📛 Waifu nomini yuboring:")


async def _rarity_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for rarity in RARITY_ORDER:
        if rarity == "Divine":
            continue
        row.append(InlineKeyboardButton(rarity, callback_data=f"rarity_{rarity}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("✨ Divine", callback_data="rarity_Divine")])
    return InlineKeyboardMarkup(rows)


async def received_rarity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await require_admin(update, context):
        return
    state = context.user_data.get(ADM_STATE)
    if state != S_RARITY:
        await query.answer("Bu callback hozir faol emas.", show_alert=True)
        return
    data = context.user_data.get(ADM_DATA, {})
    rarity = normalize_rarity(query.data.split("_", 1)[1])
    data["rarity"] = rarity
    _set_state(context, S_PRICE, data)
    await query.edit_message_text(
        f"⭐ Rarity tanlandi: <b>{rarity}</b>\n\n💰 Narxni yuboring (0 bo'lsa avtomatik rarity narxi ishlaydi).",
        parse_mode="HTML",
    )


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if not await require_admin(update, context):
        return

    state = context.user_data.get(ADM_STATE)
    data = context.user_data.get(ADM_DATA, {})

    if state == S_NAME:
        data["name"] = update.message.text.strip()
        _set_state(context, S_ANIME, data)
        await update.message.reply_text("🎌 Anime nomini yuboring:")
        return

    if state == S_ANIME:
        data["anime"] = update.message.text.strip()
        _set_state(context, S_RARITY, data)
        await update.message.reply_text(
            "⭐ Rarity ni tanlang:",
            reply_markup=await _rarity_keyboard(),
        )
        return

    if state == S_RARITY:
        rarity = normalize_rarity(update.message.text.strip())
        if rarity not in RARITY_ORDER:
            await update.message.reply_text(
                "❌ Noto'g'ri rarity.\n"
                + ", ".join(RARITY_ORDER),
            )
            return
        data["rarity"] = rarity
        _set_state(context, S_PRICE, data)
        await update.message.reply_text("💰 Narxni yuboring (raqam):")
        return

    if state == S_PRICE:
        try:
            data["price"] = int(update.message.text.strip())
        except ValueError:
            await update.message.reply_text("❌ Narx faqat raqam bo'lsin.")
            return
        _set_state(context, S_GROUP, data)
        await update.message.reply_text(
            "👥 Guruh ID yuboring.\n"
            "Agar global bo'lsa 0 yozing."
        )
        return

    if state == S_GROUP:
        raw = update.message.text.strip()
        try:
            data["group_id"] = None if raw == "0" else int(raw)
        except ValueError:
            await update.message.reply_text("❌ Guruh ID raqam bo'lishi kerak yoki 0.")
            return

        ok, wid = await waifu_db.add_waifu(
            data["name"],
            data["anime"],
            data["rarity"],
            data["file_id"],
            update.effective_user.id,
            price=int(data.get("price") or 0),
            group_id=data.get("group_id"),
        )
        if not ok:
            await update.message.reply_text("❌ Waifu qo'shib bo'lmadi.")
            _clear_state(context)
            return
        await update.message.reply_text(
            f"✅ Waifu qo'shildi: <code>#{wid}</code>\n\n"
            f"{format_waifu_card(await waifu_db.get_waifu(wid))}",
            parse_mode="HTML",
        )
        await log_db.add_log("add_waifu", user_id=update.effective_user.id, details=f"id={wid}")
        _clear_state(context)
        return


# ──────────────────────────────────────
#  CALLBACKS / DELETE / LIST
# ──────────────────────────────────────

async def handle_panel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if not await require_admin(update, context):
        return
    text = update.message.text.strip()
    role = await _get_role(update.effective_user.id)

    if role == "sub" and text not in SUB_ADMIN_BUTTONS:
        await update.message.reply_text("❌ Sub-Admin uchun bu bo'lim yopiq.")
        return

    if text == BTN_ADDWAIFU:
        await cmd_addwaifu_cmd(update, context)
        return
    if text == BTN_WAIFUS:
        await _show_waifu_list(update.message, page=0, edit=False, owner_id=update.effective_user.id if role == "sub" else None)
        return
    if text == BTN_EDITWAIFU:
        await update.message.reply_text(_usage_for_waifu_edit(), parse_mode="HTML")
        return
    if text == BTN_GROUPS:
        await cmd_group(update, context)
        return
    if text == BTN_EVENTS:
        await cmd_event(update, context)
        return
    if text == BTN_SETTINGS:
        await cmd_settings(update, context)
        return
    if text == BTN_USERS:
        await _show_users(update.message)
        return
    if text == BTN_STATS:
        await _show_stats(update.message)
        return
    if text == BTN_ADDADMIN:
        await update.message.reply_text("👑 /addadmin [user_id] [@username]")
        return
    if text == BTN_RMADMIN:
        await update.message.reply_text("🔴 /removeadmin [user_id]")
        return
    if text == BTN_BROADCAST:
        await update.message.reply_text("📣 /broadcast [xabar]")
        return
    if text == BTN_CLOSE:
        _clear_state(context)
        await update.message.reply_text("✅ Panel yopildi.", reply_markup=ReplyKeyboardRemove())
        return


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if not await log_db.is_admin(user.id):
        await query.answer("❌ Ruxsatingiz yo'q.", show_alert=True)
        return

    role = await _get_role(user.id)
    is_sub = role == "sub"

    if data == "adm_noop":
        return

    if data.startswith("adm_wlist_sub_"):
        try:
            page = int(data[len("adm_wlist_sub_"):])
        except ValueError:
            return
        await _show_waifu_list(query.message, page=page, edit=True, owner_id=user.id)
        return

    if data.startswith("adm_wlist_"):
        if is_sub:
            await query.answer("❌ Ruxsat yo'q.", show_alert=True)
            return
        try:
            page = int(data[len("adm_wlist_"):])
        except ValueError:
            return
        await _show_waifu_list(query.message, page=page, edit=True)
        return

    if data.startswith("adm_wdel_") and not data.startswith("adm_wdel_ok_") and data != "adm_wdel_cancel":
        try:
            db_id = int(data[len("adm_wdel_"):])
        except ValueError:
            return
        waifu = await waifu_db.get_waifu_by_db_id(db_id)
        if not waifu:
            await query.answer("Waifu topilmadi!", show_alert=True)
            return
        if is_sub and waifu.get("added_by") != user.id:
            await query.answer("❌ Bu waifu siz qo'shmagan.", show_alert=True)
            return
        emoji = get_rarity_emoji(waifu["rarity"])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"adm_wdel_ok_{db_id}"),
            InlineKeyboardButton("❌ Bekor", callback_data="adm_wdel_cancel"),
        ]])
        await query.message.reply_text(
            f"⚠️ <b>O'chirasizmi?</b>\n\n"
            f"{emoji} <b>{waifu['name']}</b> — {waifu['anime']}\n"
            f"Daraja: {waifu['rarity']} | 🆔 #{waifu['id']}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    if data.startswith("adm_wdel_ok_"):
        try:
            db_id = int(data[len("adm_wdel_ok_"):])
        except ValueError:
            return
        waifu = await waifu_db.get_waifu_by_db_id(db_id)
        if not waifu:
            await query.edit_message_text("❌ Waifu allaqachon o'chirilgan.")
            return
        if is_sub and waifu.get("added_by") != user.id:
            await query.answer("❌ Bu waifu siz qo'shmagan.", show_alert=True)
            return
        await waifu_db.remove_waifu_by_db_id(db_id)
        await log_db.add_log("remove_waifu", user_id=user.id, details=f"id={db_id} name={waifu['name']}")
        await query.edit_message_text(f"✅ <b>{waifu['name']}</b> (#{db_id}) o'chirildi!", parse_mode="HTML")
        return

    if data == "adm_wdel_cancel":
        await query.edit_message_text("❌ Bekor qilindi.")
        return

    if data.startswith("adm_rmch_"):
        if not is_god_admin(user.id):
            await query.answer("❌ Faqat God Admin.", show_alert=True)
            return
        ch_id = data[len("adm_rmch_"):]
        await grp_db.remove_required_channel(ch_id)
        await query.edit_message_text(f"✅ <code>{ch_id}</code> kanal o'chirildi.", parse_mode="HTML")
        return


# ──────────────────────────────────────
#  ADMIN BUYRUQLARI
# ──────────────────────────────────────

async def cmd_removewaifu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /removewaifu [#id]")
        return
    wid = context.args[0].lstrip("#")
    waifu = await waifu_db.get_waifu(wid)
    if not waifu:
        try:
            waifu = await waifu_db.get_waifu_by_db_id(int(wid))
        except ValueError:
            pass
    if not waifu:
        await update.message.reply_text(f"❌ #{wid} topilmadi.")
        return
    role = await _get_role(update.effective_user.id)
    if role == "sub" and waifu.get("added_by") != update.effective_user.id:
        await update.message.reply_text("❌ Siz qo'shmagan waifuni o'chirishingiz mumkin emas.")
        return
    await waifu_db.remove_waifu(waifu["waifu_id"])
    await update.message.reply_text(f"✅ <b>{waifu['name']}</b> (#{waifu['id']}) o'chirildi.", parse_mode="HTML")


async def cmd_spawn_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Faqat guruhda ishlaydi.")
        return
    from handlers.spawn import do_spawn
    await do_spawn(context, chat.id, chat.title)


async def _is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False
    if await log_db.is_admin(user.id):
        return True
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


async def cmd_setspawn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ Faqat guruhda.")
        return
    if not await _is_group_admin(update, context):
        await update.message.reply_text("❌ Bu buyruq faqat guruh adminlari uchun.")
        return
    if not context.args:
        current = await grp_db.get_spawn_threshold(chat.id)
        await update.message.reply_text(
            f"📊 Hozirgi spawn chegarasi: <b>{current}</b>\nFormat: /setspawn [son]",
            parse_mode="HTML",
        )
        return
    try:
        threshold = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Son kiriting.")
        return
    if threshold < 10:
        await update.message.reply_text("❌ Minimum 10.")
        return
    await grp_db.set_spawn_threshold(chat.id, threshold)
    await update.message.reply_text(f"✅ Spawn chegarasi <b>{threshold}</b> ga o'rnatildi.", parse_mode="HTML")


async def _resolve_group_id(context, text: str):
    text = text.strip()
    if text.lstrip("-").isdigit():
        return int(text), None
    username = text
    if text.startswith("https://t.me/") or text.startswith("http://t.me/"):
        path = text.split("t.me/", 1)[1].rstrip("/")
        if path.startswith("+") or "joinchat" in path:
            username = text
        else:
            username = "@" + path
    elif text.startswith("t.me/"):
        username = "@" + text.split("t.me/", 1)[1].rstrip("/")
    elif not text.startswith("@"):
        username = "@" + text
    try:
        chat = await context.bot.get_chat(username)
        return chat.id, chat.title
    except Exception as e:
        return None, str(e)


async def cmd_addgroup_bypass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "❌ Format: /addgroup [guruh_id yoki havola]\n\n"
            "Misol: /addgroup -1001234567890\n"
            "Misol: /addgroup @groupname\n"
            "Misol: /addgroup https://t.me/groupname",
            parse_mode="HTML",
        )
        return
    raw = " ".join(context.args)
    gid, info = await _resolve_group_id(context, raw)
    if gid is None:
        await update.message.reply_text(f"❌ Guruh topilmadi: {info}\nID, @username yoki havola kiriting.", parse_mode="HTML")
        return
    await grp_db.bypass_group(gid)
    if info:
        await grp_db.set_group_name(gid, info)
    await update.message.reply_text(
        f"✅ <b>Guruh qo'shildi!</b>\n"
        f"🆔 <code>{gid}</code>\n"
        f"📌 {info or gid}\n"
        f"🔓 20 ta a'zo cheklovi <b>chetlab o'tildi</b>.",
        parse_mode="HTML",
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /broadcast [xabar]")
        return
    message = " ".join(context.args)
    user_ids = await user_db.get_all_users()
    await update.message.reply_text(f"📢 {len(user_ids)} ta foydalanuvchiga yuborilmoqda...")
    sent = failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, f"📢 <b>E'lon:</b>\n\n{message}", parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.03)
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Yuborildi: {sent} | ❌ Xato: {failed}")


async def cmd_addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /addadmin [user_id] [@username]")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Raqam.")
        return
    username = context.args[1].lstrip("@") if len(context.args) > 1 else ""
    await log_db.add_admin(uid, username, update.effective_user.id, role="admin")
    await update.message.reply_text(f"✅ <code>{uid}</code> → 🔧 Admin", parse_mode="HTML")


async def cmd_addsubadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /addsubadmin [user_id] [@username]")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Raqam.")
        return
    username = context.args[1].lstrip("@") if len(context.args) > 1 else ""
    await log_db.add_admin(uid, username, update.effective_user.id, role="sub")
    await update.message.reply_text(f"✅ <code>{uid}</code> → 🟡 Sub-Admin\n<i>Common-Epic waifu qo'sha oladi.</i>", parse_mode="HTML")


async def cmd_removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /removeadmin [user_id]")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Raqam.")
        return
    await log_db.remove_admin(uid)
    await update.message.reply_text(f"✅ <code>{uid}</code> o'chirildi.", parse_mode="HTML")


async def cmd_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /banuser [user_id] [sabab]")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Raqam.")
        return
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    await user_db.ban_user(uid, reason)
    await update.message.reply_text(f"🚫 <code>{uid}</code> ban qilindi.", parse_mode="HTML")


async def cmd_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /unbanuser [user_id]")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Raqam.")
        return
    await user_db.unban_user(uid)
    await update.message.reply_text(f"✅ <code>{uid}</code> unban qilindi.", parse_mode="HTML")


async def cmd_givecoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: /givecoins [user_id] [amount]")
        return
    try:
        uid = int(context.args[0])
        amt = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Raqam kiriting.")
        return
    await user_db.add_coins(uid, amt)
    await update.message.reply_text(f"✅ <code>{uid}</code> ga +{amt:,} coin berildi.", parse_mode="HTML")


async def cmd_givewaifu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: /givewaifu [user_id] [waifu_db_id]")
        return
    try:
        uid = int(context.args[0])
        wid = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Raqam kiriting.")
        return
    waifu = await waifu_db.get_waifu_by_db_id(wid)
    if not waifu:
        await update.message.reply_text("❌ Waifu topilmadi.")
        return
    item_id = await col_db.add_to_collection(uid, waifu["waifu_id"])
    await update.message.reply_text(f"✅ Waifu berildi. Kolleksiya ID: <code>{item_id}</code>", parse_mode="HTML")


# ──────────────────────────────────────
#  EVENT SYSTEM
# ──────────────────────────────────────

async def cmd_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = _parse_cmd_text(update.message.text)
    if not args:
        await _show_event_help(update.message)
        return

    sub = args[0].lower()
    if sub in {"help", "usage"}:
        await _show_event_help(update.message)
        return

    if sub == "list":
        await _show_event_list(update.message)
        return

    if sub == "info":
        if len(args) < 2:
            await update.message.reply_text("❌ Format: /event info [event_id]")
            return
        try:
            event_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ event_id raqam bo'lsin.")
            return
        event = await event_db.get_event(event_id)
        if not event:
            await update.message.reply_text("❌ Event topilmadi.")
            return
        waifus = await event_db.get_event_waifus(event_id)
        text = _format_event(event, waifus)
        await update.message.reply_text(text, parse_mode="HTML")
        return

    if sub == "create":
        # /event create "Name" type group_id trigger_messages [description]
        if len(args) < 5:
            await update.message.reply_text(
                "❌ Format:\n<code>/event create \"Name\" type group_id trigger_messages [description]</code>",
                parse_mode="HTML",
            )
            return
        name = args[1]
        event_type = args[2]
        try:
            group_id = int(args[3])
            trigger_messages = int(args[4])
        except ValueError:
            await update.message.reply_text("❌ group_id va trigger_messages raqam bo'lsin.")
            return
        description = " ".join(args[5:]) if len(args) > 5 else ""
        event_id = await event_db.create_event(
            name=name,
            event_type=event_type,
            target_group_id=group_id,
            trigger_messages=trigger_messages,
            description=description,
            started_by=update.effective_user.id,
        )
        await update.message.reply_text(f"✅ Event yaratildi: <code>#{event_id}</code>", parse_mode="HTML")
        return

    if sub == "toggle":
        if len(args) < 3:
            await update.message.reply_text("❌ Format: /event toggle [event_id] on|off")
            return
        try:
            event_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ event_id raqam bo'lsin.")
            return
        enabled = args[2].lower() in {"on", "1", "true", "yes", "enable", "enabled"}
        await event_db.toggle_event(event_id, enabled)
        status_txt = 'yoqildi' if enabled else "o'chirildi"
        await update.message.reply_text(f"✅ Event #{event_id} {status_txt}.")
        return

    if sub == "delete":
        if len(args) < 2:
            await update.message.reply_text("❌ Format: /event delete [event_id]")
            return
        try:
            event_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ event_id raqam bo'lsin.")
            return
        await event_db.delete_event(event_id)
        await update.message.reply_text(f"✅ Event #{event_id} o'chirildi.")
        return

    if sub == "set":
        if len(args) < 4:
            await update.message.reply_text(
                "❌ Format: /event set [event_id] field value\n"
                "Maydonlar: name, event_type, target_group_id, trigger_messages, multiplier, description",
                parse_mode="HTML",
            )
            return
        try:
            event_id = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ event_id raqam bo'lsin.")
            return
        field = args[2].lower()
        value = " ".join(args[3:])
        if field in {"target_group_id", "trigger_messages"}:
            try:
                value = int(value)
            except ValueError:
                await update.message.reply_text("❌ Raqam kiritish kerak.")
                return
        elif field == "multiplier":
            try:
                value = float(value)
            except ValueError:
                await update.message.reply_text("❌ Multiplier raqam bo'lsin.")
                return
        await event_db.update_event_field(event_id, field, value)
        await update.message.reply_text(f"✅ Event #{event_id} yangilandi.")
        return

    if sub == "addwaifu":
        if len(args) < 4:
            await update.message.reply_text("❌ Format: /event addwaifu [event_id] [waifu_db_id] [price] [weight]")
            return
        try:
            event_id = int(args[1])
            waifu_db_id = int(args[2])
            price = int(args[3])
            weight = int(args[4]) if len(args) > 4 else 100
        except ValueError:
            await update.message.reply_text("❌ Raqamlar noto'g'ri.")
            return
        waifu = await waifu_db.get_waifu_by_db_id(waifu_db_id)
        if not waifu:
            await update.message.reply_text("❌ Waifu topilmadi.")
            return
        await event_db.add_event_waifu(event_id, waifu["waifu_id"], price=price, weight=weight)
        await update.message.reply_text(f"✅ Event #{event_id} ga waifu qo'shildi: <code>#{waifu_db_id}</code>", parse_mode="HTML")
        return

    if sub == "rmwaifu":
        if len(args) < 3:
            await update.message.reply_text("❌ Format: /event rmwaifu [event_id] [waifu_db_id]")
            return
        try:
            event_id = int(args[1])
            waifu_db_id = int(args[2])
        except ValueError:
            await update.message.reply_text("❌ Raqamlar noto'g'ri.")
            return
        waifu = await waifu_db.get_waifu_by_db_id(waifu_db_id)
        if not waifu:
            await update.message.reply_text("❌ Waifu topilmadi.")
            return
        await event_db.remove_event_waifu(event_id, waifu["waifu_id"])
        await update.message.reply_text(f"✅ Event #{event_id} dan waifu o'chirildi: <code>#{waifu_db_id}</code>", parse_mode="HTML")
        return

    await _show_event_help(update.message)


async def _show_event_help(message):
    text = (
        "⚡ <b>EVENT BOSHQARUV</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<code>/event list</code>\n"
        "<code>/event info [event_id]</code>\n"
        "<code>/event create \"Name\" type group_id trigger_messages [description]</code>\n"
        "<code>/event toggle [event_id] on|off</code>\n"
        "<code>/event set [event_id] field value</code>\n"
        "<code>/event addwaifu [event_id] [waifu_db_id] [price] [weight]</code>\n"
        "<code>/event rmwaifu [event_id] [waifu_db_id]</code>\n"
        "Maydonlar: name, event_type, target_group_id, trigger_messages, multiplier, description"
    )
    await message.reply_text(text, parse_mode="HTML")


def _format_event(event: dict, waifus: list[dict]) -> str:
    status = "✅ YONIQ" if event.get("is_active") else "⛔ O'CHIQ"
    lines = [
        f"⚡ <b>{event['name']}</b> <code>#{event['id']}</code>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Tur: <b>{event['event_type']}</b>",
        f"Holat: <b>{status}</b>",
        f"Target group: <code>{event.get('target_group_id')}</code>",
        f"Trigger: <b>{event.get('trigger_messages')}</b> xabar",
        f"Multiplier: <b>{event.get('multiplier')}</b>",
        f"Ta'rif: {event.get('description') or '-'}",
        f"Waifular: <b>{len(waifus)}</b>",
    ]
    for ew in waifus[:10]:
        lines.append(
            f"• <code>#{ew['waifu_id']}</code> — {ew['name']} | {ew['rarity']} | price={int(ew.get('price') or 0)} | w={ew.get('weight')}"
        )
    return "\n".join(lines)


async def _show_event_list(message):
    events = await event_db.list_events()
    if not events:
        await message.reply_text("📭 Event yo'q.")
        return
    lines = ["⚡ <b>EVENTLAR</b>", "━━━━━━━━━━━━━━━━━━━━"]
    for e in events[:30]:
        status = "✅" if e.get("is_active") else "⛔"
        lines.append(
            f"{status} <code>#{e['id']}</code> {e['name']} | {e['event_type']} | group={e.get('target_group_id')} | trigger={e.get('trigger_messages')}"
        )
    await message.reply_text("\n".join(lines), parse_mode="HTML")


# ──────────────────────────────────────
#  SETTINGS / GROUPS / CHANNELS / TITLES
# ──────────────────────────────────────

async def cmd_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    args = _parse_cmd_text(update.message.text)
    if not args:
        groups = await grp_db.get_all_groups()
        if not groups:
            await update.message.reply_text("📭 Guruhlar yo'q.")
            return
        lines = ["👥 <b>GURUHlar</b>", "━━━━━━━━━━━━━━━━━━━━"]
        for g in groups[:30]:
            lines.append(
                f"<code>{g['group_id']}</code> | {g.get('group_name') or '-'} | approved={g.get('is_approved')} | threshold={g.get('spawn_threshold')}"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    sub = args[0].lower()
    if sub in {"add", "create"} and len(args) >= 2:
        raw = " ".join(args[1:])
        gid, info = await _resolve_group_id(context, raw)
        if gid is None:
            await update.message.reply_text(f"❌ Guruh topilmadi: {info}")
            return
        await grp_db.bypass_group(gid)
        if info:
            await grp_db.set_group_name(gid, info)
        await update.message.reply_text(f"✅ Guruh qo'shildi: <code>{gid}</code>", parse_mode="HTML")
        return
    if sub == "name" and len(args) >= 3:
        try:
            gid = int(args[1])
        except ValueError:
            await update.message.reply_text("❌ group_id raqam bo'lsin.")
            return
        await grp_db.set_group_name(gid, " ".join(args[2:]))
        await update.message.reply_text("✅ Guruh nomi yangilandi.")
        return
    if sub == "threshold" and len(args) >= 3:
        try:
            gid = int(args[1])
            threshold = int(args[2])
        except ValueError:
            await update.message.reply_text("❌ Raqamlar noto'g'ri.")
            return
        await grp_db.set_spawn_threshold(gid, threshold)
        await update.message.reply_text("✅ Spawn threshold yangilandi.")
        return
    if sub == "private" and len(args) >= 3:
        try:
            gid = int(args[1])
            flag = args[2].lower() in {"1", "true", "yes", "on"}
        except ValueError:
            await update.message.reply_text("❌ Raqamlar noto'g'ri.")
            return
        await grp_db.set_group_private(gid, flag)
        await update.message.reply_text("✅ Guruh private statusi yangilandi.")
        return

    await update.message.reply_text(
        "👥 <b>Guruh boshqaruvi</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<code>/group</code> — ro'yxat\n"
        "<code>/group add [id|@username|link]</code>\n"
        "<code>/group name [group_id] [name]</code>\n"
        "<code>/group threshold [group_id] [son]</code>\n"
        "<code>/group private [group_id] [on|off]</code>",
        parse_mode="HTML",
    )


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    args = _parse_cmd_text(update.message.text)
    if not args:
        private_group = await settings_db.get_private_group_id()
        private_channel = await settings_db.get_private_channel_id()
        counter = await settings_db.get_exclusive_counter()
        await update.message.reply_text(
            "⚙️ <b>SOZLAMALAR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"Private group: <code>{private_group}</code>\n"
            f"Private channel: <code>{private_channel}</code>\n"
            f"Exclusive counter: <b>{counter}</b>\n\n"
            "<code>/settings privategroup [chat_id]</code>\n"
            "<code>/settings privatechannel [chat_id]</code>\n"
            "<code>/settings resetexclusive</code>",
            parse_mode="HTML",
        )
        return
    sub = args[0].lower()
    if sub == "privategroup" and len(args) >= 2:
        await settings_db.set_private_group_id(int(args[1]))
        await update.message.reply_text("✅ Private group saqlandi.")
        return
    if sub == "privatechannel" and len(args) >= 2:
        await settings_db.set_private_channel_id(int(args[1]))
        await update.message.reply_text("✅ Private channel saqlandi.")
        return
    if sub == "resetexclusive":
        await settings_db.reset_exclusive_counter()
        await update.message.reply_text("✅ Exclusive counter reset qilindi.")
        return
    await update.message.reply_text("❌ Noto'g'ri settings buyrug'i.")


async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if len(context.args) < 1:
        await update.message.reply_text("❌ Format: /addchannel [channel_id] [name]")
        return
    channel_id = context.args[0]
    channel_name = " ".join(context.args[1:]) if len(context.args) > 1 else channel_id
    await grp_db.add_required_channel(channel_id, channel_name, "channel", update.effective_user.id)
    await update.message.reply_text(f"✅ Kanal qo'shildi: <code>{channel_id}</code>", parse_mode="HTML")


async def cmd_removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /removechannel [channel_id]")
        return
    await grp_db.remove_required_channel(context.args[0])
    await update.message.reply_text("✅ Kanal o'chirildi.")


async def cmd_approvegroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /approvegroup [group_id]")
        return
    gid = int(context.args[0])
    await grp_db.approve_group(gid, update.effective_user.id)
    await update.message.reply_text("✅ Guruh approved.")


async def cmd_denygroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_god(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /denygroup [group_id]")
        return
    gid = int(context.args[0])
    await grp_db.deny_group(gid)
    await update.message.reply_text("✅ Guruh denied.")


async def cmd_settitle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: /settitle [user_id] [title]")
        return
    uid = int(context.args[0])
    title = " ".join(context.args[1:])
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_titles (user_id, title, given_by) VALUES ($1,$2,$3) "
            "ON CONFLICT (user_id) DO UPDATE SET title=$2, given_by=$3, given_at=NOW()",
            uid,
            title,
            update.effective_user.id,
        )
    await update.message.reply_text("✅ Unvon berildi.")


async def cmd_removetitle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_full_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("❌ Format: /removetitle [user_id]")
        return
    uid = int(context.args[0])
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_titles WHERE user_id=$1", uid)
    await update.message.reply_text("✅ Unvon olib tashlandi.")


async def cmd_titles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM user_titles ORDER BY given_at DESC LIMIT 50")
    if not rows:
        await update.message.reply_text("📭 Unvonlar yo'q.")
        return
    lines = ["🏅 <b>UNVONLAR</b>", "━━━━━━━━━━━━━━━━━━━━"]
    for r in rows:
        lines.append(f"<code>{r['user_id']}</code> — {r['title']}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    admins = await log_db.get_admins()
    role_mark = {"god": "👑 God Admin", "admin": "🔧 Admin", "sub": "🟡 Sub-Admin"}
    lines = ["🛡️ <b>ADMINLAR RO'YXATI</b>\n━━━━━━━━━━━━━━━━━━━━"]
    for a in admins:
        r = a.get("role") or "admin"
        mark = role_mark.get(r, "🔧 Admin")
        uname = f"@{a['username']}" if a.get("username") else ""
        lines.append(f"{mark}: <code>{a['user_id']}</code> {uname}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# legacy aliases
async def cmd_eventcreate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await cmd_event(update, context)


async def cmd_eventlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await cmd_event(update, context)
