import logging
import os
import sys

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from bot.conversation import build_conversation_handler
from bot.flow_loader import FlowDefinition, load_all_flows
from bot.state_store import StateStore

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value


async def global_error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    logger.exception("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado. Por favor intenta de nuevo o usa /cancelar."
        )


_FLOW_ICONS = {
    "daily": "📋",
    "incidencia": "🚨",
}


def _build_menu(flows: list[FlowDefinition]) -> tuple[str, InlineKeyboardMarkup]:
    buttons = [
        [InlineKeyboardButton(
            f"{_FLOW_ICONS.get(f.flow_id, '▶️')} {f.title}",
            callback_data=f"flow:{f.flow_id}",
        )]
        for f in flows
    ]
    text = "👋 *¡Hola! Soy el bot de reportes de Tecopos.*\n\n¿Qué deseas hacer hoy?"
    return text, InlineKeyboardMarkup(buttons)


def _build_start_handler(menu_text: str, menu_keyboard: InlineKeyboardMarkup):
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            menu_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=menu_keyboard,
        )

    return CommandHandler("start", start)


def main() -> None:
    bot_token = _require_env("BOT_TOKEN")
    admin_chat_id = int(_require_env("ADMIN_CHAT_ID"))

    flows = load_all_flows("flows")
    logger.info("Loaded %d flow(s): %s", len(flows), [f.flow_id for f in flows])

    store = StateStore()
    menu_text, menu_keyboard = _build_menu(flows)

    async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=menu_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=menu_keyboard,
        )

    app = ApplicationBuilder().token(bot_token).build()
    app.add_error_handler(global_error_handler)

    # /start menu — registered before ConversationHandlers so it's always reachable
    app.add_handler(_build_start_handler(menu_text, menu_keyboard))

    for flow in flows:
        handler = build_conversation_handler(flow, store, admin_chat_id, on_end=send_main_menu)
        app.add_handler(handler)
        logger.info("Registered flow '%s' → command %s", flow.flow_id, flow.command)

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
