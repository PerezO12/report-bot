import logging
import os
import sys

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from bot.conversation import build_conversation_handler
from bot.database import init_db
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


async def _init_app():
    bot_token = _require_env("BOT_TOKEN")
    admin_chat_id = int(_require_env("ADMIN_CHAT_ID"))

    use_proxy = os.getenv("USE_PROXY", "false").strip().lower() == "true"
    proxy_url = os.getenv("PROXY_URL", "http://proxy.server:3128").strip()

    # Initialize DB
    db = await init_db("botdaily.db")

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

    builder = ApplicationBuilder().token(bot_token)
    if use_proxy:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
        logger.info("Proxy enabled: %s", proxy_url)

    app = builder.build()
    app.add_error_handler(global_error_handler)

    # /start menu — registered before ConversationHandlers so it's always reachable
    app.add_handler(_build_start_handler(menu_text, menu_keyboard))

    for flow in flows:
        handler = build_conversation_handler(flow, store, admin_chat_id, on_end=send_main_menu, db=db)
        app.add_handler(handler)
        logger.info("Registered flow '%s' → command %s", flow.flow_id, flow.command)

    logger.info("Bot is running. Press Ctrl+C to stop.")
    return app


def main() -> None:
    import asyncio
    import sys

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = loop.run_until_complete(_init_app())

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received.")
    finally:
        # El loop puede ya estar cerrado por run_polling
        if not loop.is_closed():
            # PASO 1: Detener el updater
            logger.info("Deteniendo updater...")
            try:
                loop.run_until_complete(app.updater.stop())
            except Exception as e:
                logger.warning("Error stopping updater: %s", e)

            # PASO 2: Hacer shutdown de la aplicación
            logger.info("Haciendo shutdown de aplicación...")
            try:
                loop.run_until_complete(app.shutdown())
            except Exception as e:
                logger.warning("Error in shutdown: %s", e)

            # PASO 3: Cerrar el event loop
            logger.info("Cerrando event loop...")
            loop.close()

        # PASO 4: Salir completamente del proceso
        logger.info("Bot detenido.")
        try:
            sys.exit(0)  # Intenta cleanup ordenado
        except:
            os._exit(0)  # Fallback: mata inmediatamente


if __name__ == "__main__":
    main()
