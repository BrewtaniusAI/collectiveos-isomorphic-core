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
        if not isinstance(template, dict):
            continue
        procedures = template.get("procedure_ids")
        actuators = template.get("actuator_ids")
        verifiers = template.get("verifier_ids")
        if not all(
            isinstance(value, list) and value for value in (procedures, actuators, verifiers)
        ):
            continue
        required = [*procedures, *actuators, *verifiers]
        if any(capability_id not in available for capability_id in required):
            continue
        if template.get("output_authority") not in _ALLOWED_OUTPUT_AUTHORITY:
            continue
        if template.get("locality") not in _ALLOWED_LOCALITY:
            continue
        if template.get("cost_class") not in _ALLOWED_COST_CLASS:
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
