import logging
from functools import partial
from typing import Any

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

from .flow_loader import FlowDefinition, StepDefinition, get_next_step_id
from .formatter import format_summary
from .state_store import StateStore
from .validator import normalize_answer, run_validation

logger = logging.getLogger(__name__)


def build_states_map(flow: FlowDefinition) -> dict[str, int]:
    return {step.id: idx for idx, step in enumerate(flow.steps)}


def _make_keyboard(step_def: StepDefinition) -> InlineKeyboardMarkup | None:
    if not step_def.keyboard or not step_def.keyboard.enabled:
        return None
    if step_def.keyboard.layout == "row":
        row = [
            InlineKeyboardButton(b.label, callback_data=b.value)
            for b in step_def.keyboard.buttons
        ]
        return InlineKeyboardMarkup([row])
    # column layout
    buttons = [
        [InlineKeyboardButton(b.label, callback_data=b.value)]
        for b in step_def.keyboard.buttons
    ]
    return InlineKeyboardMarkup(buttons)


def _get_hint(step_def: StepDefinition) -> str:
    """Generate auto hint based on validation type."""
    vtype = step_def.validation.type
    if vtype == "date_selector":
        return "\n👆 _Selecciona la fecha_"
    if vtype in ("boolean", "options"):
        return "\n👆 _Selecciona una opción_"
    if vtype == "media":
        return "\n📎 _Envía una foto o vídeo_"
    if vtype == "number":
        return "\n🔢 _Escribe un número_"
    if vtype == "photo":
        return "\n📷 _Envía una foto_"
    # text, date, email, regex
    return "\n📝 _Escribe tu respuesta_"


async def _send_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step_def: StepDefinition,
) -> None:
    keyboard = _make_keyboard(step_def)
    msg = update.effective_message
    question_text = step_def.question + _get_hint(step_def)
    await msg.reply_text(
        question_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def _finish_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> int:
    user = update.effective_user
    state = store.get_state(user.id)
    if not state:
        return ConversationHandler.END

    summary = format_summary(flow, state, user)

    # Confirm to the user
    await update.effective_message.reply_text(
        "✅ *Reporte enviado correctamente.* ¡Gracias!",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Send text summary to admin
    await context.bot.send_message(
        chat_id=admin_chat_id,
        text=summary,
        parse_mode=ParseMode.MARKDOWN,
    )

    # Send media to admin if any media step was answered
    for step_id, media_info in state.media_file_ids.items():
        if not media_info:
            continue
        file_id = media_info.get("file_id")
        media_type = media_info.get("media_type", "photo")
        caption = (
            f"📎 Evidencia adjunta al reporte de *{flow.title}*\n"
            f"Enviado por: {user.first_name or ''} (@{user.username or user.id})"
        )
        if media_type == "photo":
            await context.bot.send_photo(
                chat_id=admin_chat_id,
                photo=file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )
        elif media_type == "video":
            await context.bot.send_video(
                chat_id=admin_chat_id,
                video=file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )
        elif media_type == "document":
            await context.bot.send_document(
                chat_id=admin_chat_id,
                document=file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )

    # Save to DB if applicable
    if db and flow.flow_id == "daily":
        from bot.database import save_daily

        report_date = state.answers.get("step_date", "")
        await save_daily(db, user.id, user.username or "", report_date, state.answers)

    if db and flow.flow_id == "incidencia":
        from bot.database import save_incidencia

        await save_incidencia(db, user.id, user.username or "", state.answers)

    store.clear_session(user.id)

    if on_end:
        await on_end(update, context)

    return ConversationHandler.END


async def _handle_text_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> int:
    user = update.effective_user
    current_state = states_map[step_def.id]

    try:
        valid, error_msg = run_validation(step_def, update.message)
        if not valid:
            await update.message.reply_text(
                f"⚠️ {error_msg}", parse_mode=ParseMode.MARKDOWN
            )
            return current_state

        raw_value = (update.message.text or "").strip()
        canonical = normalize_answer(step_def, raw_value)
        store.set_answer(user.id, step_def.id, canonical)

        state = store.get_state(user.id)
        next_id = get_next_step_id(step_def, state.answers)

        if next_id is None:
            return await _finish_flow(update, context, flow, store, admin_chat_id, on_end, db)

        next_step = flow.steps_by_id[next_id]
        await _send_question(update, context, next_step)
        return states_map[next_id]

    except Exception:
        logger.exception(
            "Unexpected error in step '%s' for user %d", step_def.id, user.id
        )
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado. Por favor intenta de nuevo o usa /cancelar."
        )
        return states_map[step_def.id]


async def _handle_callback_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> int:
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    current_state = states_map[step_def.id]

    try:
        raw_value = query.data or ""
        canonical = normalize_answer(step_def, raw_value)
        store.set_answer(user.id, step_def.id, canonical)

        # Edit original message to remove keyboard and show selection
        selected_label = raw_value
        for btn in (step_def.keyboard.buttons if step_def.keyboard else []):
            if btn.value == raw_value:
                selected_label = btn.label
                break
        await query.edit_message_text(
            f"{step_def.question}\n\n_Seleccionaste: {selected_label}_",
            parse_mode=ParseMode.MARKDOWN,
        )

        state = store.get_state(user.id)
        next_id = get_next_step_id(step_def, state.answers)

        if next_id is None:
            return await _finish_flow(update, context, flow, store, admin_chat_id, on_end, db)

        next_step = flow.steps_by_id[next_id]
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=next_step.question,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_make_keyboard(next_step),
        )
        return states_map[next_id]

    except Exception:
        logger.exception(
            "Unexpected error in callback step '%s' for user %d", step_def.id, user.id
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Ocurrió un error inesperado. Por favor intenta de nuevo o usa /cancelar.",
        )
        return current_state


async def _handle_photo_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> int:
    user = update.effective_user
    current_state = states_map[step_def.id]

    try:
        if not update.message.photo:
            await update.message.reply_text(
                "⚠️ Por favor envía una *foto* como evidencia.\n"
                "_Si no tienes evidencia, envía_ /skip _para continuar._",
                parse_mode=ParseMode.MARKDOWN,
            )
            return current_state

        # Take the highest resolution version (last in the list)
        file_id = update.message.photo[-1].file_id
        store.set_photo(user.id, step_def.id, file_id)

        state = store.get_state(user.id)
        next_id = get_next_step_id(step_def, state.answers)

        if next_id is None:
            return await _finish_flow(update, context, flow, store, admin_chat_id, on_end, db)

        next_step = flow.steps_by_id[next_id]
        await _send_question(update, context, next_step)
        return states_map[next_id]

    except Exception:
        logger.exception(
            "Unexpected error in photo step '%s' for user %d", step_def.id, user.id
        )
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado. Por favor intenta de nuevo o usa /cancelar."
        )
        return current_state


async def _handle_skip_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> int:
    user = update.effective_user

    if not step_def.optional:
        await update.message.reply_text(
            "⚠️ Este paso no es opcional. Por favor envía una foto para continuar."
        )
        return states_map[step_def.id]

    store.set_photo(user.id, step_def.id, None)

    state = store.get_state(user.id)
    next_id = get_next_step_id(step_def, state.answers)

    if next_id is None:
        return await _finish_flow(update, context, flow, store, admin_chat_id, on_end)

    next_step = flow.steps_by_id[next_id]
    await _send_question(update, context, next_step)
    return states_map[next_id]


async def _wrong_input_in_photo_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step_def: StepDefinition,
    states_map: dict[str, int],
) -> int:
    skip_hint = "\n_O envía_ /skip _para omitir este paso._" if step_def.optional else ""
    await update.message.reply_text(
        f"⚠️ Se espera una *foto* en este paso.{skip_hint}",
        parse_mode=ParseMode.MARKDOWN,
    )
    return states_map[step_def.id]


async def _handle_date_selector_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> int:
    """Handle date_selector callback."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    # callback_data is ISO date string: "2026-05-22"
    iso_date = query.data or ""
    if not iso_date:
        await query.edit_message_text("⚠️ Selección inválida, intenta de nuevo.")
        return states_map[step_def.id]

    # Convert ISO to DD/MM/YYYY
    try:
        parts = iso_date.split("-")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        date_str = f"{day:02d}/{month:02d}/{year}"
    except (ValueError, IndexError):
        await query.edit_message_text("⚠️ Selección inválida, intenta de nuevo.")
        return states_map[step_def.id]

    store.set_answer(user.id, step_def.id, date_str)

    # Edit message to show selection
    await query.edit_message_text(
        f"{step_def.question}\n\n_Seleccionaste: {date_str}_",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Advance to next step
    state = store.get_state(user.id)
    next_id = get_next_step_id(step_def, state.answers)

    if next_id is None:
        return await _finish_flow(update, context, flow, store, admin_chat_id, on_end)

    next_step = flow.steps_by_id[next_id]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=next_step.question + _get_hint(next_step),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_make_keyboard(next_step),
    )
    return states_map[next_id]


async def _handle_media_step(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> int:
    """Handle media step — accepts photo, video, or document."""
    user = update.effective_user
    current_state = states_map[step_def.id]

    try:
        file_id = None
        media_type = None

        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            media_type = "photo"
        elif update.message.video:
            file_id = update.message.video.file_id
            media_type = "video"
        elif update.message.document:
            file_id = update.message.document.file_id
            media_type = "document"

        if not file_id or not media_type:
            await update.message.reply_text(
                "⚠️ Por favor envía una *foto* o *vídeo* como evidencia.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return current_state

        store.set_media(user.id, step_def.id, file_id, media_type)

        state = store.get_state(user.id)
        next_id = get_next_step_id(step_def, state.answers)

        if next_id is None:
            return await _finish_flow(update, context, flow, store, admin_chat_id, on_end, db)

        next_step = flow.steps_by_id[next_id]
        await _send_question(update, context, next_step)
        return states_map[next_id]

    except Exception:
        logger.exception("Unexpected error in media step '%s' for user %d", step_def.id, user.id)
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado. Por favor intenta de nuevo o usa /cancelar."
        )
        return current_state


async def _wrong_input_in_media_state(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step_def: StepDefinition,
    states_map: dict[str, int],
) -> int:
    """Guard handler for non-media input during media step."""
    await update.message.reply_text(
        "⚠️ Por favor envía una *foto* o *vídeo* como evidencia.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return states_map[step_def.id]


def _build_step_handlers(
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> list[Any]:
    vtype = step_def.validation.type
    has_keyboard = bool(step_def.keyboard and step_def.keyboard.enabled)

    if vtype == "date_selector":
        date_selector_fn = partial(
            _handle_date_selector_step,
            flow=flow,
            step_def=step_def,
            states_map=states_map,
            store=store,
            admin_chat_id=admin_chat_id,
            on_end=on_end,
            db=db,
        )
        return [CallbackQueryHandler(date_selector_fn)]

    if vtype == "media":
        media_fn = partial(
            _handle_media_step,
            flow=flow,
            step_def=step_def,
            states_map=states_map,
            store=store,
            admin_chat_id=admin_chat_id,
            on_end=on_end,
            db=db,
        )
        wrong_fn = partial(
            _wrong_input_in_media_state,
            step_def=step_def,
            states_map=states_map,
        )
        handlers: list[Any] = [
            MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, media_fn),
            MessageHandler(filters.TEXT & ~filters.COMMAND, wrong_fn),
        ]
        return handlers

    if vtype == "photo":
        photo_fn = partial(
            _handle_photo_step,
            flow=flow,
            step_def=step_def,
            states_map=states_map,
            store=store,
            admin_chat_id=admin_chat_id,
            on_end=on_end,
            db=db,
        )
        skip_fn = partial(
            _handle_skip_photo,
            flow=flow,
            step_def=step_def,
            states_map=states_map,
            store=store,
            admin_chat_id=admin_chat_id,
            on_end=on_end,
            db=db,
        )
        wrong_fn = partial(
            _wrong_input_in_photo_state,
            step_def=step_def,
            states_map=states_map,
        )
        handlers: list[Any] = [MessageHandler(filters.PHOTO, photo_fn)]
        if step_def.optional:
            handlers.append(CommandHandler("skip", skip_fn))
        handlers.append(
            MessageHandler(filters.TEXT & ~filters.COMMAND, wrong_fn)
        )
        return handlers

    if has_keyboard:
        callback_fn = partial(
            _handle_callback_step,
            flow=flow,
            step_def=step_def,
            states_map=states_map,
            store=store,
            admin_chat_id=admin_chat_id,
            on_end=on_end,
            db=db,
        )
        return [CallbackQueryHandler(callback_fn)]

    text_fn = partial(
        _handle_text_step,
        flow=flow,
        step_def=step_def,
        states_map=states_map,
        store=store,
        admin_chat_id=admin_chat_id,
        on_end=on_end,
        db=db,
    )
    return [MessageHandler(filters.TEXT & ~filters.COMMAND, text_fn)]


async def _start_flow_common(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    store: StateStore,
    states_map: dict[str, int],
    from_callback: bool = False,
    db=None,
) -> int:
    user = update.effective_user

    # Check for duplicate daily (only for daily flow)
    if flow.flow_id == "daily" and db:
        from bot.database import has_daily_today
        from datetime import datetime, timedelta

        today_str = (datetime.utcnow()).strftime("%d/%m/%Y")
        if await has_daily_today(db, user.id, today_str):
            msg = f"⚠️ Ya enviaste tu daily de hoy ({today_str}). Intenta mañana."
            if from_callback:
                await update.callback_query.answer(msg, show_alert=True)
                return ConversationHandler.END
            else:
                await update.message.reply_text(msg)
                return ConversationHandler.END

    first_step = flow.steps[0]
    store.init_session(user.id, flow.flow_id, first_step.id)

    if from_callback:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            f"📋 *{flow.title}*\nVamos paso a paso. Puedes cancelar en cualquier momento con /cancelar.\n",
            parse_mode=ParseMode.MARKDOWN,
        )
        keyboard = _make_keyboard(first_step)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=first_step.question + _get_hint(first_step),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
    else:
        await update.message.reply_text(
            f"📋 *{flow.title}*\nVamos paso a paso. Puedes cancelar en cualquier momento con /cancelar.\n",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_question(update, context, first_step)

    return states_map[first_step.id]


def build_conversation_handler(
    flow: FlowDefinition,
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
    db=None,
) -> ConversationHandler:
    states_map = build_states_map(flow)
    command = flow.command.lstrip("/")

    async def start_flow(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        return await _start_flow_common(
            update, context, flow, store, states_map, from_callback=False, db=db
        )

    async def start_flow_from_button(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        return await _start_flow_common(
            update, context, flow, store, states_map, from_callback=True, db=db
        )

    async def cancel(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        user = update.effective_user
        store.clear_session(user.id)
        await update.message.reply_text(
            "🚫 Operación cancelada. Puedes comenzar de nuevo cuando quieras."
        )
        if on_end:
            await on_end(update, context)
        return ConversationHandler.END

    # Build states dict: {state_int: [handlers]}
    states: dict[int, list[Any]] = {}
    for step_def in flow.steps:
        state_int = states_map[step_def.id]
        states[state_int] = _build_step_handlers(
            flow, step_def, states_map, store, admin_chat_id, on_end, db
        )

    return ConversationHandler(
        entry_points=[
            CommandHandler(command, start_flow),
            CallbackQueryHandler(start_flow_from_button, pattern=f"^flow:{flow.flow_id}$"),
        ],
        states=states,
        fallbacks=[CommandHandler("cancelar", cancel)],
        per_user=True,
        per_chat=True,
        per_message=False,
        allow_reentry=True,
        name=flow.flow_id,
    )
