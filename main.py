import logging
import os
import sys

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes

from bot.conversation import build_conversation_handler
from bot.flow_loader import load_all_flows
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


def main() -> None:
    bot_token = _require_env("BOT_TOKEN")
    admin_chat_id = int(_require_env("ADMIN_CHAT_ID"))

    flows = load_all_flows("flows")
    logger.info("Loaded %d flow(s): %s", len(flows), [f.flow_id for f in flows])

    store = StateStore()

    app = ApplicationBuilder().token(bot_token).build()
    app.add_error_handler(global_error_handler)

    for flow in flows:
        handler = build_conversation_handler(flow, store, admin_chat_id)
        app.add_handler(handler)
        logger.info("Registered flow '%s' → command %s", flow.flow_id, flow.command)

    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
