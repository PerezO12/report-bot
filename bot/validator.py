import re
from datetime import datetime

from telegram import Message

from .flow_loader import StepDefinition


def validate_text(value: str) -> tuple[bool, str | None]:
    if not value or not value.strip():
        return False, "Por favor ingresa una respuesta válida (no puede estar vacía)."
    return True, None


def validate_number(
    value: str, min_val: float | None = None, max_val: float | None = None
) -> tuple[bool, str | None]:
    try:
        num = float(value.replace(",", "."))
    except ValueError:
        return False, "Por favor ingresa solo un número válido.\n*Ej:* 7.5 ó 8"
    if min_val is not None and num < min_val:
        return False, f"El valor mínimo permitido es {min_val}."
    if max_val is not None and num > max_val:
        return False, f"El valor máximo permitido es {max_val}."
    return True, None


def validate_date(value: str, fmt: str = "DD/MM/YYYY") -> tuple[bool, str | None]:
    py_fmt = fmt.replace("DD", "%d").replace("MM", "%m").replace("YYYY", "%Y")
    try:
        datetime.strptime(value.strip(), py_fmt)
    except ValueError:
        example = datetime.now().strftime(py_fmt)
        return (
            False,
            f"Formato de fecha incorrecto. Usa el formato *{fmt}*\n*Ej:* {example}",
        )
    return True, None


def validate_email(value: str) -> tuple[bool, str | None]:
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, value.strip()):
        return (
            False,
            "Por favor ingresa un correo electrónico válido.\n*Ej:* usuario@dominio.com",
        )
    return True, None


def validate_regex(value: str, pattern: str) -> tuple[bool, str | None]:
    try:
        if not re.match(pattern, value.strip()):
            return False, "El formato ingresado no es válido. Por favor revisa el formato requerido."
    except re.error:
        return False, "Error interno de validación. Contacta al administrador."
    return True, None


def validate_options(value: str, choices: list[str]) -> tuple[bool, str | None]:
    normalized = [c.lower() for c in choices]
    if value.lower() not in normalized:
        opts = ", ".join(f"*{c}*" for c in choices)
        return False, f"Opción no válida. Por favor selecciona una de: {opts}"
    return True, None


def validate_boolean(value: str, choices: list[str]) -> tuple[bool, str | None]:
    # Accept button callback values ("yes"/"no") or display labels
    valid_values = {"yes", "no"} | {c.lower() for c in choices}
    if value.lower() not in valid_values:
        opts = " / ".join(f"*{c}*" for c in choices)
        return False, f"Por favor usa los botones para responder: {opts}"
    return True, None


def validate_photo(message: Message) -> tuple[bool, str | None]:
    if not message.photo:
        return (
            False,
            "Por favor envía una *foto* como evidencia.\nSi no tienes evidencia, envía /skip para omitir.",
        )
    return True, None


def run_validation(
    step_def: StepDefinition, message: Message
) -> tuple[bool, str | None]:
    vtype = step_def.validation.type

    if vtype == "photo":
        return validate_photo(message)

    # For all non-photo types, extract text from message
    text = (message.text or "").strip()
    if not text:
        if vtype != "photo":
            return False, "Por favor ingresa una respuesta de texto."

    if vtype == "text":
        return validate_text(text)
    elif vtype == "number":
        return validate_number(
            text,
            min_val=step_def.validation.min,
            max_val=step_def.validation.max,
        )
    elif vtype == "date":
        return validate_date(text, fmt=step_def.validation.date_format)
    elif vtype == "email":
        return validate_email(text)
    elif vtype == "regex":
        return validate_regex(text, step_def.validation.pattern or "")
    elif vtype == "options":
        return validate_options(text, step_def.validation.choices)
    elif vtype == "boolean":
        return validate_boolean(text, step_def.validation.choices)

    return True, None


def normalize_answer(step_def: StepDefinition, raw_value: str) -> str:
    """Return a canonical form of the answer for storage and conditional branching."""
    vtype = step_def.validation.type
    if vtype == "boolean":
        v = raw_value.lower()
        # Map display labels to canonical yes/no
        choices = [c.lower() for c in step_def.validation.choices]
        if v == "yes" or (len(choices) >= 1 and v == choices[0]):
            return "yes"
        return "no"
    if vtype == "number":
        try:
            return str(float(raw_value.replace(",", ".")))
        except ValueError:
            return raw_value
    return raw_value.strip()
