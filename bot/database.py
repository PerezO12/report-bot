import json
import logging
from datetime import datetime

import aiosqlite

logger = logging.getLogger(__name__)


async def init_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            report_date TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            answers_json TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS incidencia_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            submitted_at TEXT NOT NULL,
            answers_json TEXT NOT NULL
        )
        """
    )
    await db.commit()
    logger.info("Database initialized: %s", path)
    return db


async def has_daily_today(db: aiosqlite.Connection, user_id: int, date_str: str) -> bool:
    """Check if user already submitted a daily for the given date (DD/MM/YYYY format)."""
    async with db.execute(
        "SELECT 1 FROM daily_reports WHERE user_id = ? AND report_date = ?",
        (user_id, date_str),
    ) as cursor:
        result = await cursor.fetchone()
    return result is not None


async def save_daily(
    db: aiosqlite.Connection, user_id: int, username: str, date_str: str, answers: dict
) -> None:
    """Save a completed daily report."""
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        INSERT INTO daily_reports (user_id, username, report_date, submitted_at, answers_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, username, date_str, now, json.dumps(answers, ensure_ascii=False)),
    )
    await db.commit()
    logger.info("Daily saved for user %d, date %s", user_id, date_str)


async def save_incidencia(
    db: aiosqlite.Connection, user_id: int, username: str, answers: dict
) -> None:
    """Save a completed incidencia report."""
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        INSERT INTO incidencia_reports (user_id, username, submitted_at, answers_json)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, username, now, json.dumps(answers, ensure_ascii=False)),
    )
    await db.commit()
    logger.info("Incidencia saved for user %d", user_id)
