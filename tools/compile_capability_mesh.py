from __future__ import annotations

from typing import Any

from tools.capability_inventory import available_capability_ids, validate_inventory

_ALLOWED_OUTPUT_AUTHORITY = {"proposal", "candidate", "evidence"}
_ALLOWED_LOCALITY = {"local", "remote", "hybrid"}
_ALLOWED_COST_CLASS = {"free", "metered", "unknown"}


def _valid_templates(templates: dict[str, Any]) -> bool:
    if templates.get("schema") != "collective.capability-binding-templates.v1":
        return False
    if templates.get("status") != "DECLARATIVE_NON_AUTHORIZING":
        return False
    return isinstance(templates.get("templates"), list)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _nonempty_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_nonempty_string(item) for item in value)


def _template_shape_valid(template: dict[str, Any]) -> bool:
    return (
        _nonempty_string(template.get("binding_id"))
        and _nonempty_string(template.get("input_artifact"))
        and _nonempty_string(template.get("output_artifact"))
        and _nonempty_string_list(template.get("procedure_ids"))
        and _nonempty_string_list(template.get("actuator_ids"))
        and _nonempty_string_list(template.get("verifier_ids"))
        and template.get("output_authority") in _ALLOWED_OUTPUT_AUTHORITY
        and template.get("locality") in _ALLOWED_LOCALITY
        and template.get("cost_class") in _ALLOWED_COST_CLASS
    )


def _roles_match(
    by_id: dict[str, dict[str, Any]],
    procedures: list[str],
    actuators: list[str],
    verifiers: list[str],
) -> bool:
    return (
        all(by_id[item]["kind"] == "procedure" for item in procedures)
        and all(by_id[item]["kind"] == "actuator" for item in actuators)
        and all(by_id[item]["kind"] == "verifier" for item in verifiers)
    )


def compile_mesh(inventory: dict[str, Any], templates: dict[str, Any]) -> dict[str, Any]:
    graph: dict[str, Any] = {
        "schema": "collective.capability-graph.v1",
        "status": "DECLARATIVE_NON_AUTHORIZING",
        "bindings": [],
        "authority": {
            "routing_is_advisory": True,
            "authorizes_execution": False,
            "authorizes_external_writes": False,
            "authorizes_canonical_commit": False,
            "authorizes_governance_promotion": False,
        },
    }

    if validate_inventory(inventory) or not _valid_templates(templates):
        return graph

    available = available_capability_ids(inventory)
    by_id = {item["capability_id"]: item for item in inventory["capabilities"]}
    compiled: list[dict[str, Any]] = []

    for template in templates["templates"]:
        if not isinstance(template, dict) or not _template_shape_valid(template):
            continue

        procedures = template["procedure_ids"]
        actuators = template["actuator_ids"]
        verifiers = template["verifier_ids"]
        required = [*procedures, *actuators, *verifiers]
        if any(capability_id not in available for capability_id in required):
            continue
        if not _roles_match(by_id, procedures, actuators, verifiers):
            continue

        providers = sorted({by_id[capability_id]["provider"] for capability_id in required})
        compiled.append(
            {
                "binding_id": template["binding_id"],
                "skill_id": " + ".join(procedures),
                "actuator": " + ".join(actuators),
                "input_artifact": template["input_artifact"],
                "output_artifact": template["output_artifact"],
                "output_authority": template["output_authority"],
                "verifier": " + ".join(verifiers),
                "verification_required": True,
                "locality": template["locality"],
                "cost_class": template["cost_class"],
                "providers": providers,
            }
        )

    graph["bindings"] = sorted(compiled, key=lambda item: item["binding_id"])
    return graph
