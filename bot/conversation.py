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


async def _send_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    step_def: StepDefinition,
) -> None:
    keyboard = _make_keyboard(step_def)
    msg = update.effective_message
    await msg.reply_text(
        step_def.question,
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

    # Send photo to admin if any photo step was answered
    for step_id, file_id in state.photo_file_ids.items():
        if file_id:
            caption = (
                f"📷 Evidencia adjunta al reporte de *{flow.title}*\n"
                f"Enviado por: {user.first_name or ''} (@{user.username or user.id})"
            )
            await context.bot.send_photo(
                chat_id=admin_chat_id,
                photo=file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )

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
            return await _finish_flow(update, context, flow, store, admin_chat_id, on_end)

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
            return await _finish_flow(update, context, flow, store, admin_chat_id, on_end)

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
            return await _finish_flow(update, context, flow, store, admin_chat_id, on_end)

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


def _build_step_handlers(
    flow: FlowDefinition,
    step_def: StepDefinition,
    states_map: dict[str, int],
    store: StateStore,
    admin_chat_id: int,
    on_end=None,
) -> list[Any]:
    vtype = step_def.validation.type
    has_keyboard = bool(step_def.keyboard and step_def.keyboard.enabled)

    if vtype == "photo":
        photo_fn = partial(
            _handle_photo_step,
            flow=flow,
            step_def=step_def,
            states_map=states_map,
            store=store,
            admin_chat_id=admin_chat_id,
            on_end=on_end,
        )
        skip_fn = partial(
            _handle_skip_photo,
            flow=flow,
            step_def=step_def,
            states_map=states_map,
            store=store,
            admin_chat_id=admin_chat_id,
            on_end=on_end,
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
    )
    return [MessageHandler(filters.TEXT & ~filters.COMMAND, text_fn)]


async def _start_flow_common(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    flow: FlowDefinition,
    store: StateStore,
    states_map: dict[str, int],
    from_callback: bool = False,
) -> int:
    user = update.effective_user
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
            text=first_step.question,
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
) -> ConversationHandler:
    states_map = build_states_map(flow)
    command = flow.command.lstrip("/")

    async def start_flow(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        return await _start_flow_common(update, context, flow, store, states_map, from_callback=False)

    async def start_flow_from_button(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        return await _start_flow_common(update, context, flow, store, states_map, from_callback=True)

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
            flow, step_def, states_map, store, admin_chat_id, on_end
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
