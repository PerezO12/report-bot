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


async def add_apk(db: aiosqlite.Connection, name: str) -> bool:
    """Add a new APK. Returns True if inserted, False if already exists."""
    try:
        await db.execute("INSERT INTO apks (name) VALUES (?)", (name,))
        await db.commit()
        logger.info(f"APK added: {name}")
        return True
    except Exception as e:
        logger.warning(f"APK '{name}' already exists or error: {e}")
        return False


async def add_module(db: aiosqlite.Connection, name: str) -> bool:
    """Add a new module. Returns True if inserted, False if already exists."""
    try:
        await db.execute("INSERT INTO modules (name) VALUES (?)", (name,))
        await db.commit()
        logger.info(f"Module added: {name}")
        return True
    except Exception as e:
        logger.warning(f"Module '{name}' already exists or error: {e}")
        return False


async def get_incidencias(
    db: aiosqlite.Connection,
    limit: int = 10,
    offset: int = 0,
    date_str: str | None = None,
    region: str | None = None,
) -> list[dict]:
    """Get incidencia reports. Optionally filter by date (DD/MM/YYYY) or region."""
    query = "SELECT id, user_id, username, submitted_at, answers_json FROM incidencia_reports ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
    async with db.execute(query, (limit, offset)) as cursor:
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        answers = json.loads(row[4])

        # Apply date filter if provided
        if date_str:
            submitted_date = row[3].split("T")[0]  # ISO to "YYYY-MM-DD"
            provided_date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            if submitted_date != provided_date:
                continue

        # Apply region filter if provided
        if region and answers.get("step_region", "").lower() != region.lower():
            continue

        results.append({
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "submitted_at": row[3],
            "answers": answers,
        })

    return results


async def get_solicitudes(
    db: aiosqlite.Connection,
    limit: int = 10,
    offset: int = 0,
    date_str: str | None = None,
    apk_name: str | None = None,
) -> list[dict]:
    """Get solicitud reports. Optionally filter by date (DD/MM/YYYY) or APK name."""
    query = "SELECT id, user_id, username, submitted_at, answers_json FROM solicitud_reports ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
    async with db.execute(query, (limit, offset)) as cursor:
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        answers = json.loads(row[4])

        # Apply date filter if provided
        if date_str:
            submitted_date = row[3].split("T")[0]
            provided_date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            if submitted_date != provided_date:
                continue

        # Apply APK filter if provided
        if apk_name and answers.get("step_apk", "").lower() != apk_name.lower():
            continue

        results.append({
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "submitted_at": row[3],
            "answers": answers,
        })

    return results


async def get_daily_reports(
    db: aiosqlite.Connection,
    limit: int = 10,
    offset: int = 0,
    date_str: str | None = None,
    user_id: int | None = None,
) -> list[dict]:
    """Get daily reports. Optionally filter by date (DD/MM/YYYY) or user_id."""
    query = "SELECT id, user_id, username, report_date, submitted_at, answers_json FROM daily_reports ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
    async with db.execute(query, (limit, offset)) as cursor:
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        # Apply date filter if provided
        if date_str and row[3] != date_str:
            continue

        # Apply user_id filter if provided
        if user_id and row[1] != user_id:
            continue

        results.append({
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "report_date": row[3],
            "submitted_at": row[4],
            "answers": json.loads(row[5]),
        })

    return results


async def count_incidencias(
    db: aiosqlite.Connection,
    date_str: str | None = None,
    region: str | None = None,
) -> int:
    """Count incidencias. If filters provided, count after filtering."""
    if not date_str and not region:
        async with db.execute("SELECT COUNT(*) FROM incidencia_reports") as cursor:
            return (await cursor.fetchone())[0]

    # Manual count with filtering
    query = "SELECT answers_json, submitted_at FROM incidencia_reports"
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()

    count = 0
    for row in rows:
        answers = json.loads(row[0])

        if date_str:
            submitted_date = row[1].split("T")[0]
            provided_date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            if submitted_date != provided_date:
                continue

        if region and answers.get("step_region", "").lower() != region.lower():
            continue

        count += 1

    return count


async def count_solicitudes(
    db: aiosqlite.Connection,
    date_str: str | None = None,
    apk_name: str | None = None,
) -> int:
    """Count solicitudes. If filters provided, count after filtering."""
    if not date_str and not apk_name:
        async with db.execute("SELECT COUNT(*) FROM solicitud_reports") as cursor:
            return (await cursor.fetchone())[0]

    # Manual count with filtering
    query = "SELECT answers_json, submitted_at FROM solicitud_reports"
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()

    count = 0
    for row in rows:
        answers = json.loads(row[0])

        if date_str:
            submitted_date = row[1].split("T")[0]
            provided_date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            if submitted_date != provided_date:
                continue

        if apk_name and answers.get("step_apk", "").lower() != apk_name.lower():
            continue

        count += 1

    return count


async def count_daily_reports(
    db: aiosqlite.Connection,
    date_str: str | None = None,
    user_id: int | None = None,
) -> int:
    """Count daily reports. If filters provided, count after filtering."""
    if not date_str and not user_id:
        async with db.execute("SELECT COUNT(*) FROM daily_reports") as cursor:
            return (await cursor.fetchone())[0]

    query = "SELECT user_id, report_date FROM daily_reports"
    async with db.execute(query) as cursor:
        rows = await cursor.fetchall()

    count = 0
    for row in rows:
        if date_str and row[1] != date_str:
            continue
        if user_id and row[0] != user_id:
            continue
        count += 1

    return count
