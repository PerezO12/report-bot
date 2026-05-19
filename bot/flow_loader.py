import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationDef:
    type: str
    date_format: str = "DD/MM/YYYY"
    pattern: str | None = None
    min: float | None = None
    max: float | None = None
    choices: list[str] = field(default_factory=list)


@dataclass
class KeyboardButton:
    label: str
    value: str


@dataclass
class KeyboardDef:
    enabled: bool
    layout: str
    buttons: list[KeyboardButton]


@dataclass
class StepDefinition:
    id: str
    question: str
    validation: ValidationDef
    optional: bool
    keyboard: KeyboardDef | None
    next_step: Any  # str | dict | None


@dataclass
class FlowDefinition:
    flow_id: str
    command: str
    title: str
    steps: list[StepDefinition]
    summary_template: str
    steps_by_id: dict[str, StepDefinition] = field(default_factory=dict)


_VALID_TYPES = {"text", "number", "date", "email", "regex", "options", "boolean", "photo"}


def _parse_validation(raw: dict, step_id: str) -> ValidationDef:
    vtype = raw.get("type")
    if vtype not in _VALID_TYPES:
        raise ValueError(
            f"Step '{step_id}': validation type '{vtype}' is invalid. "
            f"Must be one of: {', '.join(sorted(_VALID_TYPES))}"
        )
    return ValidationDef(
        type=vtype,
        date_format=raw.get("date_format", "DD/MM/YYYY"),
        pattern=raw.get("pattern"),
        min=raw.get("min"),
        max=raw.get("max"),
        choices=raw.get("choices", []),
    )


def _parse_keyboard(raw: dict | None, step_id: str) -> KeyboardDef | None:
    if not raw:
        return None
    buttons = [
        KeyboardButton(label=b["label"], value=b["value"])
        for b in raw.get("buttons", [])
    ]
    return KeyboardDef(
        enabled=raw.get("enabled", True),
        layout=raw.get("layout", "row"),
        buttons=buttons,
    )


def load_flow(path: str) -> FlowDefinition:
    p = Path(path)
    try:
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in '{path}': {e}") from e
    except OSError as e:
        raise ValueError(f"Cannot read flow file '{path}': {e}") from e

    for key in ("flow_id", "command", "title", "steps", "summary_template"):
        if key not in data:
            raise ValueError(f"Flow file '{path}' is missing required key: '{key}'")

    if not isinstance(data["steps"], list) or len(data["steps"]) == 0:
        raise ValueError(f"Flow file '{path}': 'steps' must be a non-empty list")

    steps: list[StepDefinition] = []
    step_ids: set[str] = set()

    for raw_step in data["steps"]:
        sid = raw_step.get("id")
        if not sid:
            raise ValueError(f"Flow file '{path}': a step is missing the 'id' field")
        if sid in step_ids:
            raise ValueError(f"Flow file '{path}': duplicate step id '{sid}'")
        step_ids.add(sid)

        if "question" not in raw_step:
            raise ValueError(f"Step '{sid}' in '{path}' is missing 'question'")
        if "validation" not in raw_step:
            raise ValueError(f"Step '{sid}' in '{path}' is missing 'validation'")

        steps.append(
            StepDefinition(
                id=sid,
                question=raw_step["question"],
                validation=_parse_validation(raw_step["validation"], sid),
                optional=raw_step.get("optional", False),
                keyboard=_parse_keyboard(raw_step.get("keyboard"), sid),
                next_step=raw_step.get("next_step"),
            )
        )

    # Validate all next_step references
    for step in steps:
        _validate_next_step_refs(step.next_step, step.id, step_ids, path)

    flow = FlowDefinition(
        flow_id=data["flow_id"],
        command=data["command"],
        title=data["title"],
        steps=steps,
        summary_template=data["summary_template"],
    )
    flow.steps_by_id = {s.id: s for s in steps}
    return flow


def _validate_next_step_refs(
    next_step: Any, step_id: str, valid_ids: set[str], path: str
) -> None:
    if next_step is None:
        return
    if isinstance(next_step, str):
        if next_step not in valid_ids:
            raise ValueError(
                f"Step '{step_id}' in '{path}': next_step references unknown step '{next_step}'"
            )
        return
    if isinstance(next_step, dict):
        if next_step.get("type") != "conditional":
            raise ValueError(
                f"Step '{step_id}' in '{path}': next_step dict must have type='conditional'"
            )
        for case_val, target in next_step.get("cases", {}).items():
            if target is not None and target not in valid_ids:
                raise ValueError(
                    f"Step '{step_id}' in '{path}': conditional case '{case_val}' "
                    f"references unknown step '{target}'"
                )
        default = next_step.get("default")
        if default is not None and default not in valid_ids:
            raise ValueError(
                f"Step '{step_id}' in '{path}': conditional default references unknown step '{default}'"
            )
        return
    raise ValueError(
        f"Step '{step_id}' in '{path}': next_step must be a string, null, or a conditional object"
    )


def get_next_step_id(step_def: StepDefinition, answers: dict[str, Any]) -> str | None:
    ns = step_def.next_step
    if ns is None:
        return None
    if isinstance(ns, str):
        return ns
    # Conditional
    on_step = ns.get("on", step_def.id)
    answer = answers.get(on_step)
    cases = ns.get("cases", {})
    # Normalize answer for lookup
    normalized = str(answer).lower() if answer is not None else ""
    return cases.get(normalized, ns.get("default"))


def load_all_flows(flows_dir: str) -> list[FlowDefinition]:
    flows = []
    for json_path in sorted(Path(flows_dir).glob("*.json")):
        try:
            flow = load_flow(str(json_path))
            flows.append(flow)
        except ValueError as e:
            print(f"[ERROR] Failed to load flow '{json_path}': {e}", file=sys.stderr)
            sys.exit(1)
    if not flows:
        print(f"[ERROR] No flow JSON files found in '{flows_dir}'", file=sys.stderr)
        sys.exit(1)
    return flows
