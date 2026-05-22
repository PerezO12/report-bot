import json
import logging
from datetime import datetime

import aiosqlite

logger = logging.getLogger(__name__)


async def init_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)

    # Reports tables
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
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS solicitud_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            submitted_at TEXT NOT NULL,
            answers_json TEXT NOT NULL
        )
        """
    )

    # Master data tables
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS apks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS modules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS priorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            level INTEGER NOT NULL
        )
        """
    )

    await db.commit()

    # Seed initial data
    await _seed_initial_data(db)

    logger.info("Database initialized: %s", path)
    return db


async def _seed_initial_data(db: aiosqlite.Connection) -> None:
    """Seed APKs, modules, and priorities if they don't exist."""

    # APKs
    apks = [
        "APK Punto de Venta",
        "APK Sísmico",
        "APK GESTIÓN PLUS",
        "APK KIOSKO",
        "APK TURNO",
        "Administración",
        "Otro",
    ]
    for apk in apks:
        await db.execute(
            "INSERT OR IGNORE INTO apks (name) VALUES (?)",
            (apk,)
        )

    # Modules
    modules = [
        "Dashboard",
        "Centro de alertas",
        "Mis almacenes",
        "Contenedores",
        "Logística",
        "Mis productos",
        "Producción",
        "Proveedores",
        "Facturación",
        "Registros",
        "Ciclos económicos",
        "Cuentas bancarias",
        "Salarios",
        "Clientes",
        "Reportes análisis",
        "Notificaciones",
        "Cartelera digital",
        "Promociones tienda online",
        "Turnos",
        "Usuarios",
        "Configuraciones",
        "Otro",
    ]
    for module in modules:
        await db.execute(
            "INSERT OR IGNORE INTO modules (name) VALUES (?)",
            (module,)
        )

    # Priorities
    priorities = [
        ("Baja", 1),
        ("Normal", 2),
        ("Medio", 3),
        ("Alta", 4),
        ("Urgente", 5),
        ("Extremadamente urgente", 6),
    ]
    for name, level in priorities:
        await db.execute(
            "INSERT OR IGNORE INTO priorities (name, level) VALUES (?, ?)",
            (name, level)
        )

    await db.commit()
    logger.info("Initial data seeded successfully")


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


async def save_solicitud(
    db: aiosqlite.Connection, user_id: int, username: str, answers: dict
) -> None:
    """Save a completed solicitud report."""
    now = datetime.utcnow().isoformat()
    await db.execute(
        """
        INSERT INTO solicitud_reports (user_id, username, submitted_at, answers_json)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, username, now, json.dumps(answers, ensure_ascii=False)),
    )
    await db.commit()
    logger.info("Solicitud saved for user %d", user_id)


async def get_apks(db: aiosqlite.Connection) -> list[str]:
    """Get all available APKs."""
    async with db.execute("SELECT name FROM apks ORDER BY name") as cursor:
        rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def get_modules(db: aiosqlite.Connection) -> list[str]:
    """Get all available modules."""
    async with db.execute("SELECT name FROM modules ORDER BY name") as cursor:
        rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def get_priorities(db: aiosqlite.Connection) -> list[str]:
    """Get all available priorities ordered by level."""
    async with db.execute("SELECT name FROM priorities ORDER BY level") as cursor:
        rows = await cursor.fetchall()
    return [row[0] for row in rows]
