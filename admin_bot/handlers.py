import json
import logging
from datetime import datetime, timedelta
from functools import partial
from typing import Any

import aiosqlite
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from admin_bot.renderer import (
    render_daily_card,
    render_incidencia_card,
    render_list,
    render_solicitud_card,
)
from bot.database import (
    add_apk,
    add_module,
    count_daily_reports,
    count_incidencias,
    count_solicitudes,
    get_apks,
    get_daily_reports,
    get_incidencias,
    get_modules,
    get_priorities,
    get_solicitudes,
)

logger = logging.getLogger(__name__)

# ConversationHandler states
STATE_WAITING_ITEM_NAME = 1


def _check_admin(user_id: int, admin_ids: list[int]) -> bool:
    """Verify user is authorized as admin."""
    return user_id in admin_ids


def _build_main_menu() -> InlineKeyboardMarkup:
    """Build the main menu keyboard."""
    buttons = [
        [InlineKeyboardButton("📦 APKs", callback_data="menu:apks")],
        [InlineKeyboardButton("📱 Módulos", callback_data="menu:modules")],
        [InlineKeyboardButton("🚨 Incidencias", callback_data="menu:incidencias")],
        [InlineKeyboardButton("📝 Solicitudes", callback_data="menu:solicitudes")],
        [InlineKeyboardButton("📊 Dailies", callback_data="menu:dailies")],
        [InlineKeyboardButton("⚙️ Administradores", callback_data="menu:admins")],
    ]
    return InlineKeyboardMarkup(buttons)


def _build_date_selector_keyboard(offset_days: int = 0) -> InlineKeyboardMarkup:
    """Build a keyboard with 8 date buttons (today + 7 past days)."""
    today = datetime.utcnow().date() + timedelta(days=offset_days)
    buttons = []

    # Button 0: Today
    today_str = today.strftime("%d/%m")
    buttons.append([InlineKeyboardButton(
        f"📅 Hoy — {today_str}",
        callback_data=today.strftime("%d/%m/%Y")
    )])

    # Buttons 1-7: Last 7 days
    day_labels = ["Ayer", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
    for i in range(1, 8):
        past_date = today - timedelta(days=i)
        date_str = past_date.strftime("%d/%m")
        day_label = day_labels[i - 1]
        buttons.append([InlineKeyboardButton(
            f"{day_label} {date_str}",
            callback_data=past_date.strftime("%d/%m/%Y")
        )])

    buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="menu:main")])
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command — show main menu."""
    user = update.effective_user

    if not _check_admin(user.id, context.bot_data.get("admin_user_ids", [])):
        await update.message.reply_text("⛔ Acceso denegado. Solo administradores autorizados.")
        return

    await update.message.reply_text(
        "*🤖 Panel de Administración*\n\n¿Qué quieres hacer?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_build_main_menu(),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main callback router."""
    query = update.callback_query
    user_id = update.effective_user.id
    admin_ids = context.bot_data.get("admin_user_ids", [])

    if not _check_admin(user_id, admin_ids):
        await query.answer("⛔ Acceso denegado", show_alert=True)
        return

    await query.answer()
    data = query.data or ""
    db = context.bot_data.get("db")

    if data.startswith("menu:"):
        await _handle_menu(query, data[5:], db, context)
    elif data.startswith("apk:"):
        await _handle_apk(query, data[4:], db, context)
    elif data.startswith("mod:"):
        await _handle_module(query, data[4:], db, context)
    elif data.startswith("inc:"):
        await _handle_incidencia(query, data[4:], db, context)
    elif data.startswith("sol:"):
        await _handle_solicitud(query, data[4:], db, context)
    elif data.startswith("daily:"):
        await _handle_daily(query, data[6:], db, context)
    elif data.startswith("admin:"):
        await _handle_admin(query, data[6:], db, context)


async def _handle_menu(
    query, submenu: str, db: aiosqlite.Connection, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Route menu selections."""
    if submenu == "main":
        await query.edit_message_text(
            "*🤖 Panel de Administración*\n\n¿Qué quieres hacer?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_build_main_menu(),
        )
    elif submenu == "apks":
        await _show_apk_menu(query, db)
    elif submenu == "modules":
        await _show_modules_menu(query, db)
    elif submenu == "incidencias":
        await _show_incidencias_menu(query, db)
    elif submenu == "solicitudes":
        await _show_solicitudes_menu(query, db)
    elif submenu == "dailies":
        await _show_dailies_menu(query, db)
    elif submenu == "admins":
        await _show_admins_menu(query, db)


# ============================================================================
# APKs
# ============================================================================

async def _show_apk_menu(query, db: aiosqlite.Connection) -> None:
    """Show APK management menu."""
    buttons = [
        [InlineKeyboardButton("📋 Ver APKs", callback_data="apk:list")],
        [InlineKeyboardButton("➕ Agregar APK", callback_data="apk:add")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        "*📦 APKs*\n\nOpciones disponibles:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_apk(query, action: str, db: aiosqlite.Connection, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle APK actions."""
    if action == "list":
        apks = await get_apks(db)
        text = "*📦 APKs Disponibles*\n\n"
        text += "\n".join(f"• {apk}" for apk in apks)
        text += "\n\n_Total: " + str(len(apks)) + "_"

        buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="menu:apks")]]
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif action == "add":
        await query.edit_message_text(
            "*➕ Agregar APK*\n\nEscribe el nombre de la nueva APK:",
            parse_mode=ParseMode.MARKDOWN,
        )
        context.user_data["pending_add"] = "apk"


async def _confirm_add_item(
    update: Update, context: ContextTypes.DEFAULT_TYPE, item_type: str, db: aiosqlite.Connection
) -> int:
    """Confirm adding a new APK, module, or admin user."""
    value = update.message.text.strip()

    if not value:
        await update.message.reply_text("❌ El valor no puede estar vacío.")
        return STATE_WAITING_ITEM_NAME

    if item_type == "apk":
        success = await add_apk(db, value)
        msg_type = "APK"
    elif item_type == "module":
        success = await add_module(db, value)
        msg_type = "Módulo"
    elif item_type == "admin":
        try:
            user_id = int(value)
            from bot.database import add_authorized_admin
            success = await add_authorized_admin(db, user_id)
            msg_type = f"Administrador ({user_id})"
        except ValueError:
            await update.message.reply_text("❌ El User ID debe ser un número.")
            return STATE_WAITING_ITEM_NAME
    else:
        success = False
        msg_type = "Item"

    if success:
        await update.message.reply_text(
            f"✅ {msg_type} añadido correctamente.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            f"⚠️ El {msg_type} ya existe o error al agregar.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # Show main menu again
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="*🤖 Panel de Administración*\n\n¿Qué quieres hacer?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_build_main_menu(),
    )
    return ConversationHandler.END


# ============================================================================
# Módulos
# ============================================================================

async def _show_modules_menu(query, db: aiosqlite.Connection) -> None:
    """Show modules management menu."""
    buttons = [
        [InlineKeyboardButton("📋 Ver Módulos", callback_data="mod:list")],
        [InlineKeyboardButton("➕ Agregar Módulo", callback_data="mod:add")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        "*📱 Módulos*\n\nOpciones disponibles:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_module(query, action: str, db: aiosqlite.Connection, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle module actions."""
    if action == "list":
        modules = await get_modules(db)
        text = "*📱 Módulos Disponibles*\n\n"
        text += "\n".join(f"• {mod}" for mod in modules)
        text += "\n\n_Total: " + str(len(modules)) + "_"

        buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="menu:modules")]]
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif action == "add":
        await query.edit_message_text(
            "*➕ Agregar Módulo*\n\nEscribe el nombre del nuevo módulo:",
            parse_mode=ParseMode.MARKDOWN,
        )
        context.user_data["pending_add"] = "module"


# ============================================================================
# Incidencias
# ============================================================================

async def _show_incidencias_menu(query, db: aiosqlite.Connection) -> None:
    """Show incidencias menu."""
    buttons = [
        [InlineKeyboardButton("📋 Ver Todas", callback_data="inc:list:all:0")],
        [InlineKeyboardButton("📅 Por Fecha", callback_data="inc:filter:date")],
        [InlineKeyboardButton("🌍 Por Región", callback_data="inc:filter:region")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        "*🚨 Incidencias*\n\nOpciones disponibles:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_incidencia(query, action: str, db: aiosqlite.Connection, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incidencia actions."""
    parts = action.split(":")

    if parts[0] == "list":
        offset = int(parts[2]) if len(parts) > 2 else 0
        reports = await get_incidencias(db, limit=10, offset=offset)
        total = await count_incidencias(db)

        if not reports:
            text = "*🚨 Incidencias*\n\n_No hay incidencias registradas._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="menu:incidencias")]]
        else:
            cards = [render_incidencia_card(r) for r in reports]
            text = render_list(cards, "incidencia", offset, total, "Incidencias")

            buttons = []
            if offset > 0:
                buttons.append(InlineKeyboardButton("← Anterior", callback_data=f"inc:list:all:{offset - 10}"))
            if offset + 10 < total:
                buttons.append(InlineKeyboardButton("Siguiente →", callback_data=f"inc:list:all:{offset + 10}"))

            buttons_row = [buttons] if buttons else []
            buttons_row.append([InlineKeyboardButton("🔙 Volver", callback_data="menu:incidencias")])

            buttons = InlineKeyboardMarkup(buttons_row) if buttons_row else InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="menu:incidencias")]])

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=buttons,
        )

    elif parts[0] == "filter":
        if parts[1] == "date":
            await query.edit_message_text(
                "*🚨 Incidencias — Por Fecha*\n\nSelecciona una fecha:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_build_date_selector_keyboard(),
            )
        elif parts[1] == "region":
            buttons = [
                [InlineKeyboardButton("Región 0", callback_data="inc:region:region_0")],
                [InlineKeyboardButton("Región 1", callback_data="inc:region:region_1")],
                [InlineKeyboardButton("Región 2", callback_data="inc:region:region_2")],
                [InlineKeyboardButton("Región 3", callback_data="inc:region:region_3")],
                [InlineKeyboardButton("Región 4", callback_data="inc:region:region_4")],
                [InlineKeyboardButton("🔙 Volver", callback_data="menu:incidencias")],
            ]
            await query.edit_message_text(
                "*🚨 Incidencias — Por Región*\n\nSelecciona una región:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    elif parts[0] == "date":
        date_str = parts[1]  # DD/MM/YYYY
        reports = await get_incidencias(db, limit=10, offset=0, date_str=date_str)
        total = await count_incidencias(db, date_str=date_str)

        if not reports:
            text = f"*🚨 Incidencias — {date_str}*\n\n_No hay incidencias en esta fecha._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="inc:filter:date")]]
        else:
            cards = [render_incidencia_card(r) for r in reports]
            text = render_list(cards, "incidencia", 0, total, f"Incidencias — {date_str}")
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="inc:filter:date")]]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif parts[0] == "region":
        region_val = parts[1]  # "region_0", etc.
        region_label = region_val.replace("region_", "Región ")
        reports = await get_incidencias(db, limit=10, offset=0, region=region_val)
        total = await count_incidencias(db, region=region_val)

        if not reports:
            text = f"*🚨 Incidencias — {region_label}*\n\n_No hay incidencias en esta región._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="inc:filter:region")]]
        else:
            cards = [render_incidencia_card(r) for r in reports]
            text = render_list(cards, "incidencia", 0, total, f"Incidencias — {region_label}")
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="inc:filter:region")]]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ============================================================================
# Solicitudes
# ============================================================================

async def _show_solicitudes_menu(query, db: aiosqlite.Connection) -> None:
    """Show solicitudes menu."""
    buttons = [
        [InlineKeyboardButton("📋 Ver Todas", callback_data="sol:list:all:0")],
        [InlineKeyboardButton("📅 Por Fecha", callback_data="sol:filter:date")],
        [InlineKeyboardButton("📱 Por APK", callback_data="sol:filter:apk")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        "*📝 Solicitudes*\n\nOpciones disponibles:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_solicitud(query, action: str, db: aiosqlite.Connection, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle solicitud actions."""
    parts = action.split(":")

    if parts[0] == "list":
        offset = int(parts[2]) if len(parts) > 2 else 0
        reports = await get_solicitudes(db, limit=10, offset=offset)
        total = await count_solicitudes(db)

        if not reports:
            text = "*📝 Solicitudes*\n\n_No hay solicitudes registradas._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="menu:solicitudes")]]
        else:
            cards = [render_solicitud_card(r) for r in reports]
            text = render_list(cards, "solicitud", offset, total, "Solicitudes")

            buttons = []
            if offset > 0:
                buttons.append(InlineKeyboardButton("← Anterior", callback_data=f"sol:list:all:{offset - 10}"))
            if offset + 10 < total:
                buttons.append(InlineKeyboardButton("Siguiente →", callback_data=f"sol:list:all:{offset + 10}"))

            buttons_row = [buttons] if buttons else []
            buttons_row.append([InlineKeyboardButton("🔙 Volver", callback_data="menu:solicitudes")])

            buttons = InlineKeyboardMarkup(buttons_row) if buttons_row else InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="menu:solicitudes")]])

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=buttons,
        )

    elif parts[0] == "filter":
        if parts[1] == "date":
            await query.edit_message_text(
                "*📝 Solicitudes — Por Fecha*\n\nSelecciona una fecha:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_build_date_selector_keyboard(),
            )
        elif parts[1] == "apk":
            apks = await get_apks(db)
            buttons = [[InlineKeyboardButton(apk, callback_data=f"sol:apk:{apk}")] for apk in apks]
            buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="menu:solicitudes")])

            await query.edit_message_text(
                "*📝 Solicitudes — Por APK*\n\nSelecciona un APK:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(buttons),
            )

    elif parts[0] == "date":
        date_str = parts[1]  # DD/MM/YYYY
        reports = await get_solicitudes(db, limit=10, offset=0, date_str=date_str)
        total = await count_solicitudes(db, date_str=date_str)

        if not reports:
            text = f"*📝 Solicitudes — {date_str}*\n\n_No hay solicitudes en esta fecha._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="sol:filter:date")]]
        else:
            cards = [render_solicitud_card(r) for r in reports]
            text = render_list(cards, "solicitud", 0, total, f"Solicitudes — {date_str}")
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="sol:filter:date")]]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif parts[0] == "apk":
        apk_name = ":".join(parts[1:])  # Handle APKs with colons (shouldn't happen but safe)
        reports = await get_solicitudes(db, limit=10, offset=0, apk_name=apk_name)
        total = await count_solicitudes(db, apk_name=apk_name)

        if not reports:
            text = f"*📝 Solicitudes — {apk_name}*\n\n_No hay solicitudes para este APK._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="sol:filter:apk")]]
        else:
            cards = [render_solicitud_card(r) for r in reports]
            text = render_list(cards, "solicitud", 0, total, f"Solicitudes — {apk_name}")
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="sol:filter:apk")]]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ============================================================================
# Dailies
# ============================================================================

async def _show_dailies_menu(query, db: aiosqlite.Connection) -> None:
    """Show dailies menu."""
    buttons = [
        [InlineKeyboardButton("📋 Ver Todas", callback_data="daily:list:all:0")],
        [InlineKeyboardButton("📅 Por Fecha", callback_data="daily:filter:date")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        "*📊 Dailies*\n\nOpciones disponibles:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_daily(query, action: str, db: aiosqlite.Connection, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle daily actions."""
    parts = action.split(":")

    if parts[0] == "list":
        offset = int(parts[2]) if len(parts) > 2 else 0
        reports = await get_daily_reports(db, limit=10, offset=offset)
        total = await count_daily_reports(db)

        if not reports:
            text = "*📊 Dailies*\n\n_No hay dailies registrados._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="menu:dailies")]]
        else:
            cards = [render_daily_card(r) for r in reports]
            text = render_list(cards, "daily", offset, total, "Dailies")

            buttons = []
            if offset > 0:
                buttons.append(InlineKeyboardButton("← Anterior", callback_data=f"daily:list:all:{offset - 10}"))
            if offset + 10 < total:
                buttons.append(InlineKeyboardButton("Siguiente →", callback_data=f"daily:list:all:{offset + 10}"))

            buttons_row = [buttons] if buttons else []
            buttons_row.append([InlineKeyboardButton("🔙 Volver", callback_data="menu:dailies")])

            buttons = InlineKeyboardMarkup(buttons_row) if buttons_row else InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="menu:dailies")]])

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=buttons,
        )

    elif parts[0] == "filter":
        if parts[1] == "date":
            await query.edit_message_text(
                "*📊 Dailies — Por Fecha*\n\nSelecciona una fecha:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_build_date_selector_keyboard(),
            )

    elif parts[0] == "date":
        date_str = parts[1]  # DD/MM/YYYY
        reports = await get_daily_reports(db, limit=10, offset=0, date_str=date_str)
        total = await count_daily_reports(db, date_str=date_str)

        if not reports:
            text = f"*📊 Dailies — {date_str}*\n\n_No hay dailies en esta fecha._"
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="daily:filter:date")]]
        else:
            cards = [render_daily_card(r) for r in reports]
            text = render_list(cards, "daily", 0, total, f"Dailies — {date_str}")
            buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="daily:filter:date")]]

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ============================================================================
# Administradores (Authorized Admin Users)
# ============================================================================

async def _show_admins_menu(query, db: aiosqlite.Connection) -> None:
    """Show admin management menu."""
    buttons = [
        [InlineKeyboardButton("👥 Ver Administradores", callback_data="admin:list")],
        [InlineKeyboardButton("➕ Agregar Admin", callback_data="admin:add")],
        [InlineKeyboardButton("🗑️ Remover Admin", callback_data="admin:remove")],
        [InlineKeyboardButton("🔙 Volver", callback_data="menu:main")],
    ]
    await query.edit_message_text(
        "*⚙️ Administradores*\n\nGestión de usuarios autorizados:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _handle_admin(query, action: str, db: aiosqlite.Connection, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin user management."""
    from bot.database import get_authorized_admins

    if action == "list":
        admin_ids = await get_authorized_admins(db)
        text = "*⚙️ Administradores Autorizados*\n\n"
        if not admin_ids:
            text += "_No hay administradores._"
        else:
            text += "\n".join(f"• `{uid}`" for uid in admin_ids)
        text += f"\n\n_Total: {len(admin_ids)}_"

        buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="menu:admins")]]
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action == "add":
        await query.edit_message_text(
            "*➕ Agregar Administrador*\n\nEscribe el User ID del nuevo administrador:\n`/cancelar` para volver",
            parse_mode=ParseMode.MARKDOWN,
        )
        context.user_data["pending_add"] = "admin"

    elif action == "remove":
        admin_ids = await get_authorized_admins(db)
        if not admin_ids:
            await query.answer("No hay administradores para remover", show_alert=True)
            return

        buttons = [[InlineKeyboardButton(f"❌ {uid}", callback_data=f"admin:confirm_remove:{uid}")] for uid in admin_ids]
        buttons.append([InlineKeyboardButton("🔙 Volver", callback_data="menu:admins")])

        await query.edit_message_text(
            "*🗑️ Remover Administrador*\n\nSelecciona quién remover:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )

    elif action.startswith("confirm_remove:"):
        user_id_str = action.split(":")[2]
        user_id = int(user_id_str)

        from bot.database import remove_authorized_admin
        success = await remove_authorized_admin(db, user_id)

        if success:
            text = f"✅ Administrador `{user_id}` removido correctamente."
        else:
            text = f"⚠️ No se pudo remover administrador `{user_id}`."

        buttons = [[InlineKeyboardButton("🔙 Volver", callback_data="menu:admins")]]
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(buttons),
        )


# ============================================================================
# ConversationHandler for adding items
# ============================================================================

def build_admin_conversation(db: aiosqlite.Connection) -> ConversationHandler:
    """Build conversation handler for adding APKs/modules."""

    async def _wait_for_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Wait for item name input."""
        item_type = context.user_data.get("pending_add", "").strip()
        if not item_type:
            return ConversationHandler.END

        confirm_fn = partial(_confirm_add_item, item_type=item_type, db=db)
        return await confirm_fn(update, context)

    return ConversationHandler(
        entry_points=[],  # Triggered programmatically from callbacks
        states={
            STATE_WAITING_ITEM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, _wait_for_item_name)]
        },
        fallbacks=[],
        per_user=True,
        per_chat=True,
    )
