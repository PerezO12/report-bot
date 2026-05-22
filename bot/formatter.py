from datetime import datetime, timezone
from typing import Any

from telegram import User
from telegram.helpers import escape_markdown

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
    return escape_markdown(str(val), version=2)


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
    media_file_ids: dict[str, dict | None],
    user: User,
) -> str:
    report_type = str(answers.get("step_type", "incidencia")).lower()

    if report_type == "solicitud":
        return _format_solicitud_summary(answers, user)
    else:
        return _format_incidencia_detail_summary(answers, media_file_ids, user)


def _format_incidencia_detail_summary(
    answers: dict[str, Any],
    media_file_ids: dict[str, dict | None],
    user: User,
) -> str:
    has_media = bool(media_file_ids.get("step_evidence"))
    lines = [
        "*🚨 REPORTE DE INCIDENCIA*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"*Enviado por:* {_user_tag(user)}",
        f"*Timestamp:* {_now_utc()}",
        "",
        f"*🌍 Región:* {_get(answers, 'step_region')}",
        f"*🏪 Negocio:* {_get(answers, 'step_business_incident')}",
        f"*🔧 Sistema/Entorno:* {_get(answers, 'step_system')}",
        "",
        "*📝 Descripción del problema:*",
        f"  {_get(answers, 'step_description')}",
        "",
        f"*✅ Confirmado por comercial:* {_get(answers, 'step_confirmed')}",
        f"*📎 Evidencia:* {'Adjunta ✅' if has_media else 'Sin evidencia'}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def _format_solicitud_summary(
    answers: dict[str, Any],
    user: User,
) -> str:
    lines = [
        "*📝 SOLICITUD DE MEJORA*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"*Enviado por:* {_user_tag(user)}",
        f"*Timestamp:* {_now_utc()}",
        "",
        f"*🏪 Negocio:* {_get(answers, 'step_business_request')}",
        f"*📱 Módulo/Aplicación:* {_get(answers, 'step_apk')}",
        "",
        "*💡 Implementación solicitada:*",
        f"  {_get(answers, 'step_implementation')}",
        "",
        "*📚 Ejemplo de uso:*",
        f"  {_get(answers, 'step_usage_example')}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)


def format_summary(flow: FlowDefinition, state: UserState, user: User) -> str:
    template = flow.summary_template
    if template == "daily":
        return format_daily_summary(state.answers, user)
    if template == "incidencia":
        return _format_incidencia_detail_summary(state.answers, state.media_file_ids, user)
    if template == "solicitud":
        return _format_solicitud_summary(state.answers, user)
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
        media = state.media_file_ids.get(step.id)
        if media:
            display = "_(📎 adjunto)_"
        else:
            display = _get(state.answers, step.id)
        label = step.question.split("\n")[0].replace("*", "").strip(" ?¿:")
        lines.append(f"*{label}:* {display}")
    lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━", f"_{_now_utc()}_"]
    return "\n".join(lines)
