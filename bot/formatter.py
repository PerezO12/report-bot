from datetime import datetime, timezone
from typing import Any

from telegram import User

from .flow_loader import FlowDefinition
from .state_store import UserState


def _user_tag(user: User) -> str:
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    if user.username:
        return f"@{user.username} ({full_name})" if full_name else f"@{user.username}"
    return full_name or str(user.id)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _get(answers: dict[str, Any], step_id: str, default: str = "—") -> str:
    val = answers.get(step_id)
    if val is None:
        return default
    return str(val)


def format_daily_summary(answers: dict[str, Any], user: User) -> str:
    blocker_answer = answers.get("step_blocker", "no")
    has_blocker = str(blocker_answer).lower() == "yes"

    meeting_answer = answers.get("step_needs_meeting", "no")
    needs_meeting = str(meeting_answer).lower() == "yes"

    lines = [
        "*📋 DAILY STANDUP REPORT*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"*Enviado por:* {_user_tag(user)}",
        f"*Fecha del reporte:* {_get(answers, 'step_date')}",
        "",
        "*🕐 Ayer trabajé en:*",
        f"  • Horas trabajadas: {_get(answers, 'step_yesterday_hours')}h",
        f"  • Descripción: {_get(answers, 'step_yesterday_desc')}",
        "",
        "*📅 Hoy planeo trabajar en:*",
        f"  {_get(answers, 'step_today')}",
        "",
    ]

    if has_blocker:
        lines += [
            "*🚧 Bloqueos:* Sí",
            f"  • Descripción: {_get(answers, 'step_blocker_desc')}",
        ]
        if needs_meeting:
            lines += [
                "  • Reunión requerida: Sí",
                f"  • Horario propuesto: {_get(answers, 'step_meeting_time')}",
            ]
        else:
            lines.append("  • Reunión requerida: No")
    else:
        lines.append("*🚧 Bloqueos:* No")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"_{_now_utc()}_",
    ]
    return "\n".join(lines)


def format_incidencia_summary(
    answers: dict[str, Any],
    photo_file_ids: dict[str, str | None],
    user: User,
) -> str:
    has_photo = bool(photo_file_ids.get("step_evidence"))
    lines = [
        "*🚨 REPORTE DE INCIDENCIA*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"*Enviado por:* {_user_tag(user)}",
        f"*Timestamp:* {_now_utc()}",
        "",
        f"*🌍 Región:* {_get(answers, 'step_region')}",
        f"*🏪 Negocio:* {_get(answers, 'step_business')}",
        f"*🔧 Módulo afectado:* {_get(answers, 'step_module')}",
        "",
        "*📝 Descripción del problema:*",
        f"  {_get(answers, 'step_description')}",
        "",
        f"*📷 Evidencia:* {'Foto adjunta ✅' if has_photo else 'Sin evidencia'}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_summary(flow: FlowDefinition, state: UserState, user: User) -> str:
    template = flow.summary_template
    if template == "daily":
        return format_daily_summary(state.answers, user)
    if template == "incidencia":
        return format_incidencia_summary(state.answers, state.photo_file_ids, user)
    # Generic fallback for any future flow
    return _format_generic(flow, state, user)


def _format_generic(flow: FlowDefinition, state: UserState, user: User) -> str:
    lines = [
        f"*📄 {flow.title.upper()}*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"*Enviado por:* {_user_tag(user)}",
        f"*Timestamp:* {_now_utc()}",
        "",
    ]
    for step in flow.steps:
        val = state.answers.get(step.id) or state.photo_file_ids.get(step.id)
        display = "_(foto adjunta)_" if step.id in state.photo_file_ids else str(val or "—")
        label = step.question.split("\n")[0].replace("*", "").strip(" ?¿:")
        lines.append(f"*{label}:* {display}")
    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", f"_{_now_utc()}_"]
    return "\n".join(lines)
