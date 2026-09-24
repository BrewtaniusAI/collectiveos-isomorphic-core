from __future__ import annotations

from typing import Any

_ALLOWED_OUTPUT_AUTHORITY = {"proposal", "candidate", "evidence"}
_REQUIRED_FALSE_AUTHORITY = (
    "authorizes_execution",
    "authorizes_external_writes",
    "authorizes_canonical_commit",
    "authorizes_governance_promotion",
)


def validate_chain(chain: dict[str, Any]) -> list[str]:
    violations: list[str] = []

    if chain.get("schema") != "collective.capability-chain.v1":
        violations.append("SCHEMA")
    if chain.get("status") != "DECLARATIVE_NON_AUTHORIZING":
        violations.append("STATUS")

    authority = chain.get("authority")
    if not isinstance(authority, dict):
        violations.append("AUTHORITY")
    else:
        if authority.get("composition_rule") != "INTERSECTION_ACROSS_ALL_LINKS_HOST_AND_POLICY":
            violations.append("COMPOSITION_RULE")
        for key in _REQUIRED_FALSE_AUTHORITY:
            if authority.get(key) is not False:
                violations.append(f"AUTHORITY:{key}")

    links = chain.get("links")
    if not isinstance(links, list) or not links:
        violations.append("LINKS")
        return violations

    seen_ids: set[str] = set()
    previous_output: str | None = None
    for index, link in enumerate(links):
        if not isinstance(link, dict):
            violations.append(f"LINK:{index}")
            continue
        link_id = link.get("link_id")
        if not isinstance(link_id, str) or not link_id:
            link_id = f"index-{index}"
            violations.append(f"LINK_ID:{link_id}")
        elif link_id in seen_ids:
            violations.append(f"DUPLICATE_LINK_ID:{link_id}")
        seen_ids.add(link_id)

        if link.get("verification_required") is not True:
            violations.append(f"VERIFICATION_REQUIRED:{link_id}")
        if link.get("output_authority") not in _ALLOWED_OUTPUT_AUTHORITY:
            violations.append(f"OUTPUT_AUTHORITY:{link_id}")

        input_artifact = link.get("input_artifact")
        output_artifact = link.get("output_artifact")
        if not isinstance(input_artifact, str) or not input_artifact:
            violations.append(f"INPUT_ARTIFACT:{link_id}")
        if not isinstance(output_artifact, str) or not output_artifact:
            violations.append(f"OUTPUT_ARTIFACT:{link_id}")
        if index > 0 and previous_output is not None and input_artifact != previous_output:
            violations.append(f"ARTIFACT_DISCONTINUITY:{link_id}")
        if isinstance(output_artifact, str) and output_artifact:
            previous_output = output_artifact

    return violations
