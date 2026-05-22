import logging
import os
import sys

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

from admin_bot.handlers import build_admin_conversation, handle_callback, start
from bot.database import init_db

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    """Get required environment variable or exit."""
    value = os.getenv(name, "").strip()
    if not value:
        logger.error("Missing required environment variable: %s", name)
        sys.exit(1)
    return value


async def global_error_handler(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle global errors."""
    logger.exception("Unhandled exception", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ Ocurrió un error inesperado. Por favor intenta de nuevo."
        )


async def _init_app():
    """Initialize the admin bot application."""
    admin_bot_token = _require_env("ADMIN_BOT_TOKEN")
    admin_user_ids_str = _require_env("ADMIN_USER_IDS")

    # Parse comma-separated user IDs
    admin_user_ids = [int(uid.strip()) for uid in admin_user_ids_str.split(",")]
    logger.info("Authorized admin users: %s", admin_user_ids)

    # Initialize database
    db = await init_db("botdaily.db")
    logger.info("Database initialized")

    # Build application
    app = ApplicationBuilder().token(admin_bot_token).build()
    app.add_error_handler(global_error_handler)

    # Store authorized user IDs and db in bot_data for use in handlers
    app.bot_data["admin_user_ids"] = admin_user_ids  # List of authorized user IDs
    app.bot_data["db"] = db

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(build_admin_conversation(db))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Admin bot is ready. Press Ctrl+C to stop.")
    return app


def main() -> None:
    """Main entry point."""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = loop.run_until_complete(_init_app())

    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received.")
    finally:
        # Cleanup
        if not loop.is_closed():
            logger.info("Shutting down...")
            try:
                loop.run_until_complete(app.updater.stop())
            except Exception as e:
                logger.warning("Error stopping updater: %s", e)

            try:
                loop.run_until_complete(app.shutdown())
            except Exception as e:
                logger.warning("Error in shutdown: %s", e)

            loop.close()

        logger.info("Admin bot stopped.")
        try:
            sys.exit(0)
        except:
            os._exit(0)


if __name__ == "__main__":
    main()
