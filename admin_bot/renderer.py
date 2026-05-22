import json
from datetime import datetime
from typing import Any

from telegram.helpers import escape_markdown


def _get_answer(answers: dict, step_id: str, default: str = "—") -> str:
    """Get answer value, escape markdown, provide default."""
    val = answers.get(step_id)
    if val is None:
        return default
    return escape_markdown(str(val), version=2)


def render_incidencia_card(row: dict) -> str:
    """Format an incidencia report for display in Telegram."""
    answers = row["answers"]
    user_tag = f"@{row['username']}" if row["username"] else f"user:{row['user_id']}"
    submitted = row["submitted_at"][:19]  # Remove timezone, keep "YYYY-MM-DD HH:MM:SS"

    lines = [
        f"*📌 Incidencia #{row['id']}*",
        f"_Por: {user_tag} · {submitted}_",
        f"*Región:* {_get_answer(answers, 'step_region')}",
        f"*Negocio:* {_get_answer(answers, 'step_business')}",
        f"*Sistema:* {_get_answer(answers, 'step_system')}",
        f"*Prioridad:* {_get_answer(answers, 'step_priority')}",
        f"*Descripción:* {_get_answer(answers, 'step_description')}",
    ]

    confirmed = _get_answer(answers, "step_confirmed", "—")
    lines.append(f"*Confirmado:* {confirmed}")

    return "\n".join(lines)


def render_solicitud_card(row: dict) -> str:
    """Format a solicitud report for display in Telegram."""
    answers = row["answers"]
    user_tag = f"@{row['username']}" if row["username"] else f"user:{row['user_id']}"
    submitted = row["submitted_at"][:19]

    lines = [
        f"*💡 Solicitud #{row['id']}*",
        f"_Por: {user_tag} · {submitted}_",
        f"*Negocio:* {_get_answer(answers, 'step_business')}",
        f"*APK:* {_get_answer(answers, 'step_apk')}",
        f"*Prioridad:* {_get_answer(answers, 'step_priority')}",
        f"*Implementación:* {_get_answer(answers, 'step_implementation')}",
        f"*Uso:* {_get_answer(answers, 'step_usage_example')}",
    ]

    return "\n".join(lines)


def render_daily_card(row: dict) -> str:
    """Format a daily report for display in Telegram."""
    answers = row["answers"]
    user_tag = f"@{row['username']}" if row["username"] else f"user:{row['user_id']}"
    report_date = row["report_date"]  # DD/MM/YYYY

    lines = [
        f"*📋 Daily #{row['id']}*",
        f"_Por: {user_tag} · Fecha: {report_date}_",
        f"*Ayer (horas):* {_get_answer(answers, 'step_yesterday_hours')}h",
        f"*Ayer (descripción):* {_get_answer(answers, 'step_yesterday_desc')}",
        f"*Hoy:* {_get_answer(answers, 'step_today')}",
    ]

    blocker = _get_answer(answers, "step_blocker", "no").lower()
    if blocker == "yes":
        lines.append(f"*Bloqueos:* Sí")
        lines.append(f"  • {_get_answer(answers, 'step_blocker_desc')}")

        needs_meeting = _get_answer(answers, "step_needs_meeting", "no").lower()
        if needs_meeting == "yes":
            lines.append(f"  • Reunión: Sí · {_get_answer(answers, 'step_meeting_time')}")
        else:
            lines.append(f"  • Reunión: No")
    else:
        lines.append(f"*Bloqueos:* No")

    return "\n".join(lines)


def render_list(
    cards: list[str],
    tipo: str,
    offset: int,
    total: int,
    title: str = "",
) -> str:
    """Format a paginated list of cards."""
    start = offset + 1
    end = min(offset + len(cards), total)

    emoji_map = {
        "incidencia": "🚨",
        "solicitud": "📝",
        "daily": "📊",
    }
    emoji = emoji_map.get(tipo, "📋")

    header = f"*{emoji} {title or tipo.capitalize()}*\n"
    header += f"_Mostrando {start}-{end} de {total}_\n\n"

    body = "\n\n".join(cards)

    return header + body
