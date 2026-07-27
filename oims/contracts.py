"""Input-first governance and output validation for every OIMS tier."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .manifest import ROOT

DEFAULT_CONTRACT_PATH = ROOT / "contracts" / "oims-family.contract.yaml"


class ContractError(ValueError):
    """Raised when a runtime contract is invalid."""


@dataclass(frozen=True)
class ContractDecision:
    status: str
    lawful: bool
    should_execute: bool
    code: str
    message: str


@dataclass(frozen=True)
class RuntimeContract:
    family: str
    version: str
    input_max_length: int
    lawful_states: tuple[str, ...]
    max_runtime_drift: float
    require_nonempty_output: bool
    source_path: Path
    source_hash: str


def load_contract(path: Path | str = DEFAULT_CONTRACT_PATH) -> RuntimeContract:
    contract_path = Path(path)
    try:
        source = contract_path.read_bytes()
        raw: dict[str, Any] = yaml.safe_load(source)
    except (OSError, yaml.YAMLError) as exc:
        raise ContractError(f"cannot load contract {contract_path}: {exc}") from exc

    try:
        preconditions = raw["preconditions"]
        invariants = raw["invariants"]
        return RuntimeContract(
            family=str(raw["family"]),
            version=str(raw["version"]),
            input_max_length=int(preconditions["input_max_length"]),
            lawful_states=tuple(str(item) for item in invariants["lawful_states"]),
            max_runtime_drift=float(invariants["max_runtime_drift"]),
            require_nonempty_output=bool(invariants["require_nonempty_output"]),
            source_path=contract_path,
            source_hash=hashlib.sha256(source).hexdigest(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError(f"invalid contract structure in {contract_path}: {exc}") from exc


def validate_input(prompt: object, contract: RuntimeContract) -> ContractDecision:
    if not isinstance(prompt, str):
        return ContractDecision(
            status="DIGITAL_APOPTOSIS",
            lawful=False,
            should_execute=False,
            code="input_not_string",
            message="Execution collapsed: input must be a string.",
        )
    if len(prompt) > contract.input_max_length:
        return ContractDecision(
            status="DIGITAL_APOPTOSIS",
            lawful=False,
            should_execute=False,
            code="input_too_long",
            message=f"Execution collapsed: input exceeds {contract.input_max_length} characters.",
        )
    if not prompt.strip():
        return ContractDecision(
            status="IDLE",
            lawful=True,
            should_execute=False,
            code="empty_input",
            message="No model executed: empty input is a governed idle condition.",
        )
    return ContractDecision(
        status="LAWFUL",
        lawful=True,
        should_execute=True,
        code="accepted",
        message="Input accepted by the family contract.",
    )


def validate_output(output: object, contract: RuntimeContract) -> ContractDecision:
    if contract.require_nonempty_output and (not isinstance(output, str) or not output.strip()):
        return ContractDecision(
            status="DIGITAL_APOPTOSIS",
            lawful=False,
            should_execute=False,
            code="empty_model_output",
            message="Execution collapsed: the model emitted no usable output.",
        )
    return ContractDecision(
        status="LAWFUL",
        lawful=True,
        should_execute=False,
        code="output_accepted",
        message="Output accepted by the family contract.",
    )
