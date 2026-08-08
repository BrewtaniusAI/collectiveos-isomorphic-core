from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import forge.oims_forge_entrypoint as forge_entrypoint
import oims.model_forge as model_forge_module
from forge.oims_forge_entrypoint import package_digest as entrypoint_package_digest
from forge.oims_forge_entrypoint import protected_mount_errors, verify_installed_package
from oims.cli import main as cli_main
from oims.manifest import ROOT
from oims.model_forge import (
    EXPECTED_TARGET_PARAMETERS,
    ForgePlanError,
    _forge_mount_policy,
    _installed_package_digest,
    _verified_execution_source,
    compute_plan_hash,
    forge_container_environment_errors,
    forge_plan_decision,
    inspect_physical_preflight,
    load_forge_plan,
    prefixed_file_digest,
    qmf_canonical_json,
    simulate_forge_run,
    validate_forge_plan,
    verify_forge_run,
)
from oims.proof import seal_record

EXAMPLE = ROOT / "forge" / "examples" / "gpt-oss-20b-4090-simulation.plan.json"
PROBE_EXAMPLE = ROOT / "forge" / "examples" / "gpt-oss-20b-4090-probe.plan.json"
TEST_VERIFIED_SOURCE = ("a" * 40, "b" * 40)
TEST_NVIDIA_SMI_PATH = "/usr/bin/nvidia-smi"


@pytest.fixture(autouse=True)
def attested_source_for_forge_exercises(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    if request.node.get_closest_marker("direct_source"):
        return
    original = model_forge_module._verified_execution_source

    def verified_source(environment: dict[str, str] | None = None) -> tuple[str, str] | None:
        return TEST_VERIFIED_SOURCE if environment is None else original(environment)

    monkeypatch.setattr(model_forge_module, "_verified_execution_source", verified_source)


def load_example() -> dict[str, object]:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def rehash(plan: dict[str, object]) -> dict[str, object]:
    plan["plan_hash"] = compute_plan_hash(plan)
    return plan


def probe_plan() -> dict[str, object]:
    return json.loads(PROBE_EXAMPLE.read_text(encoding="utf-8"))


def test_checked_in_simulation_plan_is_exact_and_fail_closed() -> None:
    plan = load_forge_plan(EXAMPLE)
    assert validate_forge_plan(plan) == ()
    decision = forge_plan_decision(plan)
    assert decision["lawful"] is True
    assert decision["qmf_admissible"] is False
    assert decision["evidence_class"] == "SIMULATED"


def test_checked_in_probe_plan_is_exact_and_non_training() -> None:
    plan = load_forge_plan(PROBE_EXAMPLE)
    assert validate_forge_plan(plan) == ()
    assert (
        plan["plan_hash"]
        == "sha256:a7d8598120a94de263af8f3d2de54e5be0da4142c10c8aeef4d1467e8266f4b6"
    )
    decision = forge_plan_decision(plan)
    assert decision["lawful"] is True
    assert decision["mode"] == "probe"
    assert decision["qmf_admissible"] is False


@pytest.mark.direct_source
def test_plan_decision_omits_unverified_source_provenance() -> None:
    with patch.dict("oims.model_forge.os.environ", {}, clear=True):
        decision = forge_plan_decision(load_example())
    assert decision["lawful"] is True
    assert decision["source_commit"] is None


def test_deeply_nested_plan_cli_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "deeply-nested.json"
    plan_path.write_text("[" * 2_000 + "0" + "]" * 2_000, encoding="utf-8")
    exit_code = cli_main(["forge", "validate", "--plan", str(plan_path)])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 64
    assert payload["status"] == "MALFORMED"
    assert "JSON nesting exceeds the supported limit" in payload["errors"][0]


def test_valid_escaped_surrogate_pair_is_normalized(tmp_path: Path) -> None:
    plan_path = tmp_path / "escaped-pair.json"
    plan_path.write_text('{"emoji":"\\ud83d\\ude00"}', encoding="utf-8")
    assert load_forge_plan(plan_path) == {"emoji": "😀"}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO inputs require POSIX")
def test_non_regular_plan_input_fails_closed_without_reading(tmp_path: Path) -> None:
    plan_fifo = tmp_path / "plan.fifo"
    os.mkfifo(plan_fifo)

    with pytest.raises(ForgePlanError, match="Forge plan must be a regular file"):
        load_forge_plan(plan_fifo)


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (("sandbox", "network_mode"), "bridge", "network_mode"),
        (("sandbox", "read_only_root"), 1, "read_only_root"),
        (("target", "local_files_only"), 1, "local_files_only"),
        (("target", "trust_remote_code"), True, "trust_remote_code"),
        (("recipe", "merge_adapter"), True, "merge_adapter"),
        (("resources", "allow_swap"), True, "allow_swap"),
        (("qmf_contract", "admissible"), True, "admissible"),
    ],
)
def test_privilege_and_identity_boundaries_refuse_drift(
    path: tuple[str, str],
    value: object,
    expected: str,
) -> None:
    plan = load_example()
    section = plan[path[0]]
    assert isinstance(section, dict)
    section[path[1]] = value
    rehash(plan)
    assert any(expected in error for error in validate_forge_plan(plan))


def test_unknown_fields_are_refused_at_every_public_level() -> None:
    for section_name in (
        None,
        "qmf_contract",
        "target",
        "sandbox",
        "resources",
        "recipe",
        "checkpoints",
        "simulation",
    ):
        plan = load_example()
        target = plan if section_name is None else plan[section_name]
        assert isinstance(target, dict)
        target["surprise"] = True
        rehash(plan)
        assert any("unknown fields" in error for error in validate_forge_plan(plan))


def test_plan_hash_and_immutable_base_rollback_are_recomputed() -> None:
    plan = load_example()
    qmf = plan["qmf_contract"]
    assert isinstance(qmf, dict)
    qmf["rollback_artifact_hash"] = "sha256:" + "f" * 64
    errors = validate_forge_plan(plan)
    assert "QMF rollback artifact must be the immutable base artifact" in errors
    assert "plan_hash does not match the canonical plan body" in errors


@pytest.mark.parametrize(
    "repository_id",
    [
        "-owner/repo",
        ".owner/repo",
        "_owner/repo",
        "owner/-repo",
        "owner/.repo",
        "owner/_repo",
    ],
)
def test_repository_segments_must_start_alphanumerically(repository_id: str) -> None:
    plan = load_example()
    qmf = plan["qmf_contract"]
    assert isinstance(qmf, dict)
    qmf["output_repository_id"] = repository_id
    rehash(plan)
    assert "qmf_contract.output_repository_id is invalid" in validate_forge_plan(plan)


def test_physical_memory_domains_cannot_be_aggregated_or_aliased() -> None:
    plan = load_example()
    resources = plan["resources"]
    assert isinstance(resources, dict)
    domains = resources["memory_domains"]
    assert isinstance(domains, list)
    domains[1]["kind"] = "gpu-vram"
    domains[1]["id"] = domains[0]["id"]
    resources["max_peak_device_bytes"] = 100 * 1024**3
    rehash(plan)
    errors = validate_forge_plan(plan)
    assert any("identifiers must be unique" in error for error in errors)
    assert any("cannot aggregate or alias" in error for error in errors)
    assert any("device_bytes exceeds" in error for error in errors)


def test_simulation_emits_verifiable_non_model_evidence(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    result = verify_forge_run(run_dir / "receipt.json")
    assert result == {
        "valid": True,
        "receipt_path": str((run_dir / "receipt.json").resolve()),
        "run_id": receipt["run_id"],
        "evidence_class": "SIMULATED",
        "qmf_admissible": False,
        "errors": [],
    }
    assert not list(run_dir.rglob("adapter_config.json"))
    assert not list(run_dir.rglob("adapter_model.safetensors"))
    candidate = json.loads(
        (run_dir / "candidate" / "synthetic-candidate.json").read_text(encoding="utf-8")
    )
    assert candidate["not_a_model"] is True
    assert candidate["not_a_peft_adapter"] is True
    assert candidate["qmf_admissible"] is False
    evidence_files = [path for path in run_dir.rglob("*") if path.is_file()]
    assert receipt["output_bytes"] == sum(path.stat().st_size for path in evidence_files)
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o755
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o644 for path in evidence_files)


def test_simulation_refuses_to_overwrite_an_existing_run(tmp_path: Path) -> None:
    plan = load_example()
    simulate_forge_run(plan, artifacts_dir=tmp_path)
    with pytest.raises(ForgePlanError, match="already exists"):
        simulate_forge_run(plan, artifacts_dir=tmp_path)


def test_simulation_cleans_staging_directory_after_write_failure(tmp_path: Path) -> None:
    plan = load_example()
    with (
        patch("oims.model_forge.atomic_write_json", side_effect=OSError("disk full")),
        pytest.raises(ForgePlanError, match="cannot persist Forge simulation evidence"),
    ):
        simulate_forge_run(plan, artifacts_dir=tmp_path)
    assert not list(tmp_path.iterdir())
    receipt = simulate_forge_run(plan, artifacts_dir=tmp_path)
    assert (tmp_path / receipt["run_id"] / "receipt.json").is_file()


def test_checkpoint_tampering_breaks_verification(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    checkpoint_path = run_dir / "checkpoints" / "step-000002.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["synthetic_loss_millionths"] -= 1
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert any("checkpoint 2 hash is invalid" in error for error in result["errors"])


def test_checkpoint_enumeration_is_bounded_before_parsing(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    checkpoint_dir = run_dir / "checkpoints"
    existing_count = len(list(checkpoint_dir.iterdir()))
    for index in range(model_forge_module.MAX_SIMULATION_STEPS + 1 - existing_count):
        (checkpoint_dir / f"untrusted-{index:06d}.json").touch()

    original_parser = model_forge_module._json_object_from_bytes
    parsed_labels: list[str] = []

    def recording_parser(payload: bytes, path: Path, label: str) -> dict[str, object]:
        parsed_labels.append(label)
        return original_parser(payload, path, label)

    with patch("oims.model_forge._json_object_from_bytes", side_effect=recording_parser):
        result = verify_forge_run(run_dir / "receipt.json")

    assert result["valid"] is False
    assert "Forge checkpoint directory exceeds the maximum checkpoint count" in result["errors"]
    assert not any(label.startswith("Forge checkpoint") for label in parsed_labels)


def test_checkpoint_aggregate_bytes_are_admitted_before_parsing(tmp_path: Path) -> None:
    plan = load_example()
    simulation = plan["simulation"]
    resources = plan["resources"]
    checkpoints = plan["checkpoints"]
    assert isinstance(simulation, dict)
    assert isinstance(resources, dict)
    assert isinstance(checkpoints, dict)
    simulation["steps"] = 15
    simulation["synthetic_loss_millionths"] = list(range(900_000, 899_985, -1))
    resources["max_steps"] = 15
    checkpoints["retain_last"] = 15
    rehash(plan)
    receipt = simulate_forge_run(plan, artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    checkpoint_dir = run_dir / "checkpoints"
    for checkpoint_path in checkpoint_dir.iterdir():
        with checkpoint_path.open("wb") as handle:
            handle.truncate(800_000)

    original_parser = model_forge_module._json_object_from_bytes
    parsed_labels: list[str] = []

    def recording_parser(payload: bytes, path: Path, label: str) -> dict[str, object]:
        parsed_labels.append(label)
        return original_parser(payload, path, label)

    with patch("oims.model_forge._json_object_from_bytes", side_effect=recording_parser):
        result = verify_forge_run(run_dir / "receipt.json")

    assert result["valid"] is False
    assert (
        "serialized Forge evidence exceeds the output byte budget before parsing"
        in result["errors"]
    )
    assert not any(label.startswith("Forge checkpoint") for label in parsed_labels)


def test_telemetry_tampering_breaks_verification(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    telemetry = run_dir / "telemetry.jsonl"
    telemetry.write_text(telemetry.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert "Forge telemetry hash is invalid" in result["errors"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO inputs require POSIX")
def test_telemetry_replacement_is_descriptor_bounded(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    telemetry = run_dir / "telemetry.jsonl"
    original_is_file = Path.is_file
    replaced = False

    def replace_after_regular_file_check(path: Path) -> bool:
        nonlocal replaced
        result = original_is_file(path)
        if path == telemetry and result and not replaced:
            path.unlink()
            os.mkfifo(path)
            replaced = True
        return result

    with patch.object(Path, "is_file", replace_after_regular_file_check):
        result = verify_forge_run(run_dir / "receipt.json")

    assert replaced is True
    assert result["valid"] is False
    assert "Forge telemetry must be a regular file" in result["errors"]


def test_resealed_forged_telemetry_still_fails_semantic_replay(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    telemetry_path = run_dir / "telemetry.jsonl"
    events = [json.loads(line) for line in telemetry_path.read_text(encoding="utf-8").splitlines()]
    events[0]["peak_host_bytes"] += 1
    telemetry_path.write_text(
        "".join(qmf_canonical_json(event) + "\n" for event in events),
        encoding="utf-8",
    )
    receipt["telemetry_hash"] = prefixed_file_digest(telemetry_path)
    receipt = seal_record(receipt)
    (run_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert "Forge telemetry failed semantic replay" in result["errors"]


@pytest.mark.parametrize(
    "relative_path",
    ["checkpoints/step-000001.json", "candidate/synthetic-candidate.json"],
)
def test_non_finite_exponent_artifacts_fail_closed(
    tmp_path: Path,
    relative_path: str,
) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    artifact = run_dir / relative_path
    text = artifact.read_text(encoding="utf-8")
    artifact.write_text(text.replace("\n}", ',\n  "overflow": 1e999\n}'), encoding="utf-8")
    result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert any("non-finite JSON number: 1e999" in error for error in result["errors"])


def test_candidate_parent_symlink_loop_fails_closed(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    candidate_dir = tmp_path / receipt["run_id"] / "candidate"
    candidate_file = candidate_dir / "synthetic-candidate.json"
    candidate_file.unlink()
    candidate_dir.rmdir()
    candidate_dir.symlink_to("candidate", target_is_directory=True)
    result = verify_forge_run(tmp_path / receipt["run_id"] / "receipt.json")
    assert result["valid"] is False
    assert any("cannot resolve Forge candidate path" in error for error in result["errors"])


def test_lone_surrogate_receipt_cli_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    receipt_path = tmp_path / receipt["run_id"] / "receipt.json"
    text = receipt_path.read_text(encoding="utf-8")
    receipt_path.write_text(
        text.replace("\n}", ',\n  "surrogate": "\\ud800"\n}'),
        encoding="utf-8",
    )
    exit_code = cli_main(["forge", "verify", "--receipt", str(receipt_path)])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["valid"] is False
    assert any("unpaired Unicode surrogate" in error for error in payload["errors"])


def test_forge_receipt_cli_defers_symlink_loop_to_guarded_verifier(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt_loop = tmp_path / "receipt-loop.json"
    receipt_loop.symlink_to(receipt_loop.name)

    exit_code = cli_main(["forge", "verify", "--receipt", str(receipt_loop)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["valid"] is False
    assert "cannot resolve Forge receipt path" in payload["errors"][0]


def test_forge_plan_cli_defers_symlink_loop_to_guarded_loader(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_loop = tmp_path / "plan-loop.json"
    plan_loop.symlink_to(plan_loop.name)

    exit_code = cli_main(["forge", "validate", "--plan", str(plan_loop)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 64
    assert payload["status"] == "MALFORMED"
    assert "cannot load Forge plan" in payload["errors"][0]


@pytest.mark.parametrize("field", ["source_commit", "source_tree"])
def test_resealed_receipt_cannot_drop_source_provenance(
    tmp_path: Path,
    field: str,
) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    receipt[field] = None
    receipt = seal_record(receipt)
    (run_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert f"Forge receipt {field} is invalid" in result["errors"]


def test_resealed_receipt_cannot_substitute_source_provenance(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    verified_source = (receipt["source_commit"], receipt["source_tree"])
    receipt["source_commit"] = "e" * 40
    receipt["source_tree"] = "f" * 40
    receipt = seal_record(receipt)
    (run_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    with patch("oims.model_forge._verified_execution_source", return_value=verified_source):
        result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert (
        "Forge receipt provenance does not match the verified execution source" in result["errors"]
    )


@pytest.mark.parametrize("field", ["telemetry_file", "checkpoint_directory", "candidate_file"])
def test_receipt_artifact_paths_fail_closed_on_embedded_nul(
    tmp_path: Path,
    field: str,
) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    receipt[field] = "\0"
    receipt = seal_record(receipt)
    (run_dir / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert f"Forge receipt field {field} is invalid" in result["errors"]


def test_receipt_input_path_fails_closed_on_embedded_nul() -> None:
    result = verify_forge_run("\0")
    assert result["valid"] is False
    assert "cannot resolve Forge receipt path" in result["errors"][0]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO inputs require POSIX")
def test_non_regular_receipt_input_fails_closed_without_reading(tmp_path: Path) -> None:
    receipt_fifo = tmp_path / "receipt.fifo"
    os.mkfifo(receipt_fifo)

    result = verify_forge_run(receipt_fifo)

    assert result["valid"] is False
    assert result["errors"] == ["Forge receipt must be a regular file"]


def test_probe_requires_exact_dual_unlock_before_device_inspection() -> None:
    plan = probe_plan()
    with patch("oims.model_forge.subprocess.run") as run:
        result = inspect_physical_preflight(
            plan,
            accepted_plan_hash="sha256:" + "0" * 64,
            environment={},
        )
    assert result["lawful"] is False
    assert result["training_started"] is False
    assert result["weights_loaded"] is False
    assert result["qmf_admissible"] is False
    assert any("accepted plan hash" in error for error in result["errors"])
    run.assert_not_called()


def test_probe_rejects_unattested_nvidia_smi_path_before_device_inspection() -> None:
    plan = probe_plan()
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
        "OIMS_FORGE_NVIDIA_RUNTIME_SHA256": "sha256:" + "d" * 64,
        "OIMS_FORGE_NVIDIA_SMI_PATH": "/forge/inputs/base/nvidia-smi",
    }
    with patch("oims.model_forge.subprocess.run") as run:
        result = inspect_physical_preflight(
            plan,
            accepted_plan_hash=plan["plan_hash"],
            environment=environment,
        )
    assert "OIMS_FORGE_NVIDIA_SMI_PATH is not an attested system executable" in result["errors"]
    run.assert_not_called()


def test_refused_probe_omits_unverified_source_provenance() -> None:
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
        "OIMS_FORGE_NVIDIA_RUNTIME_SHA256": "sha256:" + "d" * 64,
        "OIMS_FORGE_NVIDIA_SMI_PATH": TEST_NVIDIA_SMI_PATH,
        "OIMS_FORGE_CONTAINER": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "OIMS_FORGE_BASE_IMAGE": "python:3.12-slim@sha256:" + "a" * 64,
        "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
        "OIMS_FORGE_SOURCE_TREE": "b" * 40,
    }
    with patch("oims.model_forge._verified_execution_source", return_value=None):
        result = inspect_physical_preflight(
            probe_plan(),
            accepted_plan_hash=probe_plan()["plan_hash"],
            environment=environment,
        )
    assert result["status"] == "REFUSED"
    assert result["source_commit"] is None
    assert result["source_tree"] is None
    assert result["nvidia_runtime_sha256"] is None


@pytest.mark.parametrize(
    (
        "reported_uuid",
        "reported_name",
        "reported_total_memory",
        "reported_power_limit",
        "expected_error",
    ),
    [
        (
            "GPU-00000000-0000-0000-0000-000000000000",
            "NVIDIA GeForce RTX 4090",
            "24564",
            "450",
            None,
        ),
        (
            "GPU-00000000-0000-0000-0000-000000000000",
            "NVIDIA GeForce RTX 4090",
            "1e999",
            "450",
            "nvidia-smi returned malformed numeric evidence",
        ),
        (
            "",
            "NVIDIA GeForce RTX 4090",
            "24564",
            "450",
            "nvidia-smi returned an empty device UUID",
        ),
        (
            "GPU-00000000-0000-0000-0000-000000000000",
            "",
            "24564",
            "450",
            "nvidia-smi returned an empty device name",
        ),
        (
            "GPU-00000000-0000-0000-0000-000000000000",
            "NVIDIA A100-SXM4-80GB",
            "24564",
            "450",
            "physical GPU identity is not the reviewed RTX 4090 target",
        ),
        (
            "GPU-00000000-0000-0000-0000-000000000000",
            "NVIDIA GeForce RTX 4090",
            "24564",
            "0",
            "nvidia-smi returned malformed numeric evidence",
        ),
    ],
)
def test_probe_can_prove_a_locked_4090_sandbox_without_training(
    reported_uuid: str,
    reported_name: str,
    reported_total_memory: str,
    reported_power_limit: str,
    expected_error: str | None,
) -> None:
    plan = probe_plan()
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
        "OIMS_FORGE_NVIDIA_RUNTIME_SHA256": "sha256:" + "d" * 64,
        "OIMS_FORGE_NVIDIA_SMI_PATH": TEST_NVIDIA_SMI_PATH,
        "PATH": "/forge/inputs/base:/usr/bin",
        "LD_LIBRARY_PATH": "/forge/inputs/base",
        "LD_PRELOAD": "/forge/inputs/base/libnvidia-ml.so.1",
        "LD_AUDIT": "/forge/inputs/dataset/libaudit.so",
        "GLIBC_TUNABLES": "glibc.rtld.dynamic_sort=1",
        "OIMS_FORGE_CONTAINER": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "OIMS_FORGE_BASE_IMAGE": "python:3.12-slim@sha256:" + "a" * 64,
        "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
        "OIMS_FORGE_SOURCE_TREE": "b" * 40,
    }
    completed = subprocess.CompletedProcess(
        args=[TEST_NVIDIA_SMI_PATH],
        returncode=0,
        stdout=(
            f"{reported_uuid}, {reported_name}, "
            f"{reported_total_memory}, 0, 42, 20, {reported_power_limit}\n"
        ),
        stderr="",
    )
    with (
        patch(
            "oims.model_forge._proc_status",
            return_value={
                "CapEff": "0000000000000000",
                "NoNewPrivs": "1",
                "Seccomp": "2",
            },
        ),
        patch(
            "oims.model_forge._memory_info",
            return_value={
                "MemTotal": 127 * 1024**3,
                "MemAvailable": 121 * 1024**3,
                "SwapTotal": 0,
                "SwapFree": 0,
            },
        ),
        patch("oims.model_forge._root_is_read_only", return_value=True),
        patch("oims.model_forge._default_route_present", return_value=False),
        patch("oims.model_forge._network_interfaces", return_value={"lo"}),
        patch(
            "oims.model_forge._forge_mount_policy",
            return_value={
                "plan_read_only": True,
                "base_model_read_only": True,
                "dataset_read_only": True,
                "output_writable": True,
                "output_process_writable": True,
                "tmpfs_active": True,
            },
        ),
        patch(
            "oims.model_forge._cgroup_limits",
            return_value={
                "memory_limit_bytes": 124 * 1024**3,
                "memory_current_bytes": 1 * 1024**3,
                "swap_limit_bytes": 0,
                "pids_limit": 512,
            },
        ),
        patch("oims.model_forge.os.geteuid", return_value=65532),
        patch("oims.model_forge._container_source_attestation_errors", return_value=()),
        patch("oims.model_forge.subprocess.run", return_value=completed) as run,
    ):
        result = inspect_physical_preflight(
            plan,
            accepted_plan_hash=plan["plan_hash"],
            environment=environment,
        )
    assert result["status"] == ("READY" if expected_error is None else "REFUSED")
    assert result["lawful"] is (expected_error is None)
    if expected_error is None:
        assert result["gpu"]["name"] == "NVIDIA GeForce RTX 4090"
    else:
        assert result["gpu"] is None
        assert expected_error in result["errors"]
    assert result["sandbox_observation"]["host_memory_available_bytes"] == 121 * 1024**3
    assert result["nvidia_runtime_sha256"] == environment["OIMS_FORGE_NVIDIA_RUNTIME_SHA256"]
    assert result["training_started"] is False
    assert result["qmf_admissible"] is False
    run.assert_called_once()
    assert run.call_args.args[0][0] == TEST_NVIDIA_SMI_PATH
    assert run.call_args.args[0][0] != "nvidia-smi"
    assert run.call_args.kwargs["env"] == {"LC_ALL": "C"}


def test_malformed_plan_root_never_raises_from_public_validator() -> None:
    malformed_values = [None, [], "plan", 1, True, {"schema_version": object()}]
    for value in malformed_values:
        errors = validate_forge_plan(value)
        assert errors


def test_malformed_selectors_fail_closed_across_public_boundaries() -> None:
    for malformed in ([], {}):
        simulation_plan = load_example()
        simulation_plan["mode"] = malformed
        decision = forge_plan_decision(simulation_plan)
        assert decision["lawful"] is False
        assert decision["mode"] is None
        assert any("mode" in error for error in decision["errors"])

        physical_plan = probe_plan()
        resources = physical_plan["resources"]
        assert isinstance(resources, dict)
        domains = resources["memory_domains"]
        assert isinstance(domains, list)
        domains[0]["kind"] = malformed
        errors = validate_forge_plan(physical_plan)
        assert any("kind" in error for error in errors)
        receipt = inspect_physical_preflight(
            physical_plan,
            accepted_plan_hash=physical_plan["plan_hash"],
            environment={},
        )
        assert receipt["lawful"] is False
        assert receipt["qmf_admissible"] is False


def test_non_json_public_inputs_return_refusals_instead_of_raising() -> None:
    malformed_plan = probe_plan()
    malformed_plan["plan_id"] = object()
    decision = forge_plan_decision(malformed_plan)
    assert decision["lawful"] is False
    receipt = inspect_physical_preflight(
        malformed_plan,
        accepted_plan_hash=malformed_plan["plan_hash"],
        environment={},
    )
    assert receipt["lawful"] is False
    assert receipt["plan_id"] is None

    empty_id_plan = probe_plan()
    empty_id_plan["plan_id"] = ""
    empty_id_receipt = inspect_physical_preflight(
        empty_id_plan,
        accepted_plan_hash=empty_id_plan["plan_hash"],
        environment={},
    )
    assert empty_id_receipt["lawful"] is False
    assert empty_id_receipt["plan_id"] is None

    root_receipt = inspect_physical_preflight(
        None,
        accepted_plan_hash="",
        environment={},
    )
    assert root_receipt["lawful"] is False
    assert root_receipt["plan_hash"] is None

    environment_receipt = inspect_physical_preflight(
        probe_plan(),
        accepted_plan_hash="",
        environment=[],
    )
    assert environment_receipt["lawful"] is False
    assert "Forge environment must be a mapping" in environment_receipt["errors"]


def test_probe_cli_uses_fixed_receipt_name_for_invalid_plan_hash(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = probe_plan()
    plan["plan_hash"] = "x/../../../owned"
    plan_path = tmp_path / "malformed-probe.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    output_path = tmp_path / "receipts"

    with patch("oims.cli.atomic_create_json") as create_receipt:
        exit_code = cli_main(
            [
                "forge",
                "probe",
                "--plan",
                str(plan_path),
                "--accept-plan-hash",
                plan["plan_hash"],
                "--output",
                str(output_path),
            ]
        )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["lawful"] is False
    assert create_receipt.call_args.args[0] == output_path / "preflight-invalid.json"


def test_probe_mode_refuses_simulation_payload() -> None:
    plan = load_example()
    plan["mode"] = "probe"
    plan["evidence_class"] = "PHYSICAL_PREFLIGHT"
    rehash(plan)
    assert "simulation must be null for physical preflight mode" in validate_forge_plan(plan)


def test_container_input_paths_require_component_boundaries() -> None:
    for field, value in (
        ("local_model_path", "/forge/inputs/base-evil"),
        ("local_dataset_path", "/forge/inputs/dataset-backup"),
    ):
        plan = load_example()
        target = plan["target"]
        assert isinstance(target, dict)
        target[field] = value
        rehash(plan)
        assert any(field in error for error in validate_forge_plan(plan))


def test_simulation_refuses_unreplayable_timestamps_before_writing(tmp_path: Path) -> None:
    plan = load_example()
    simulation = plan["simulation"]
    assert isinstance(simulation, dict)
    simulation["clock_start"] = "9999-12-31T23:59:59+00:00"
    simulation["step_duration_seconds"] = 2
    rehash(plan)
    assert "simulation timestamps exceed the datetime range" in validate_forge_plan(plan)
    with pytest.raises(ForgePlanError, match="timestamps exceed"):
        simulate_forge_run(plan, artifacts_dir=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "clock_start",
    [
        "2026-01-01 00:00:00+00:00",
        "2026-01-01T00:00:00+00:00:30",
        "20260101T00:00:00Z",
        "2026-01-01T00:00:00,5Z",
    ],
)
def test_simulation_clock_requires_exact_rfc3339(clock_start: str) -> None:
    plan = load_example()
    simulation = plan["simulation"]
    assert isinstance(simulation, dict)
    simulation["clock_start"] = clock_start
    rehash(plan)
    assert "simulation.clock_start must be timezone-aware RFC3339" in validate_forge_plan(plan)


@pytest.mark.direct_source
def test_direct_simulation_refuses_unattested_source_before_writing(tmp_path: Path) -> None:
    with (
        patch.dict("oims.model_forge.os.environ", {}, clear=True),
        patch("oims.model_forge.subprocess.run") as git,
        pytest.raises(ForgePlanError, match="attested isolated container source"),
    ):
        simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    assert not list(tmp_path.iterdir())
    git.assert_not_called()


@pytest.mark.direct_source
def test_direct_source_rejects_git_repository_environment_overrides() -> None:
    with (
        patch.dict(
            "oims.model_forge.os.environ",
            {"GIT_DIR": "/alternate/.git", "GIT_WORK_TREE": "/alternate"},
            clear=True,
        ),
        patch("oims.model_forge.subprocess.run") as git,
    ):
        assert _verified_execution_source() is None
    git.assert_not_called()


@pytest.mark.direct_source
def test_direct_verification_refuses_unattested_loaded_source(tmp_path: Path) -> None:
    with patch("oims.model_forge._verified_execution_source", return_value=TEST_VERIFIED_SOURCE):
        receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    receipt_path = tmp_path / receipt["run_id"] / "receipt.json"
    with (
        patch.dict("oims.model_forge.os.environ", {}, clear=True),
        patch("oims.model_forge.subprocess.run") as git,
    ):
        result = verify_forge_run(receipt_path)
    assert result["valid"] is False
    assert any(
        "provenance does not match the verified execution source" in error
        for error in result["errors"]
    )
    git.assert_not_called()


@pytest.mark.parametrize(
    ("memory_info", "cgroup_limits", "host_domain_bytes", "expected_error"),
    [
        (
            {
                "MemTotal": 128 * 1024**3,
                "MemAvailable": 0,
                "SwapTotal": 0,
                "SwapFree": 0,
            },
            {
                "memory_limit_bytes": 124 * 1024**3,
                "memory_current_bytes": 1 * 1024**3,
                "swap_limit_bytes": 0,
                "pids_limit": 512,
            },
            128 * 1024**3,
            "available host memory is below the plan's host-memory ceiling",
        ),
        (
            {
                "MemTotal": 128 * 1024**3,
                "MemAvailable": 1 * 1024**3,
                "SwapTotal": 0,
                "SwapFree": 0,
            },
            {
                "memory_limit_bytes": 124 * 1024**3,
                "memory_current_bytes": 1 * 1024**3,
                "swap_limit_bytes": 0,
                "pids_limit": 512,
            },
            128 * 1024**3,
            "available host memory is below the plan's host-memory ceiling",
        ),
        (
            {
                "MemTotal": 128 * 1024**3,
                "MemAvailable": 121 * 1024**3,
                "SwapTotal": 0,
                "SwapFree": 0,
            },
            {
                "memory_limit_bytes": 120 * 1024**3,
                "memory_current_bytes": 1 * 1024**3,
                "swap_limit_bytes": 0,
                "pids_limit": 512,
            },
            128 * 1024**3,
            "available container memory is below the plan's host-memory ceiling",
        ),
        (
            {
                "MemTotal": 128 * 1024**3,
                "MemAvailable": 121 * 1024**3,
                "SwapTotal": 0,
                "SwapFree": 0,
            },
            {
                "memory_limit_bytes": 124 * 1024**3,
                "memory_current_bytes": 1 * 1024**3,
                "swap_limit_bytes": 0,
                "pids_limit": 512,
            },
            131 * 1024**3,
            "physical host memory does not match the declared memory domain",
        ),
        (
            {
                "MemTotal": 132 * 1024**3,
                "MemAvailable": 121 * 1024**3,
                "SwapTotal": 0,
                "SwapFree": 0,
            },
            {
                "memory_limit_bytes": 124 * 1024**3,
                "memory_current_bytes": 1 * 1024**3,
                "swap_limit_bytes": 0,
                "pids_limit": 512,
            },
            128 * 1024**3,
            "physical host memory does not match the declared memory domain",
        ),
    ],
)
def test_probe_requires_current_memory_headroom(
    memory_info: dict[str, int],
    cgroup_limits: dict[str, int],
    host_domain_bytes: int,
    expected_error: str,
) -> None:
    plan = probe_plan()
    resources = plan["resources"]
    assert isinstance(resources, dict)
    domains = resources["memory_domains"]
    assert isinstance(domains, list)
    host_domain = next(domain for domain in domains if domain["kind"] == "host-ram")
    host_domain["capacity_bytes"] = host_domain_bytes
    rehash(plan)
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
        "OIMS_FORGE_NVIDIA_RUNTIME_SHA256": "sha256:" + "d" * 64,
        "OIMS_FORGE_NVIDIA_SMI_PATH": TEST_NVIDIA_SMI_PATH,
        "OIMS_FORGE_CONTAINER": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "OIMS_FORGE_BASE_IMAGE": "python:3.12-slim@sha256:" + "a" * 64,
        "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
        "OIMS_FORGE_SOURCE_TREE": "b" * 40,
    }
    with (
        patch(
            "oims.model_forge._proc_status",
            return_value={"CapEff": "0000000000000000", "NoNewPrivs": "1", "Seccomp": "2"},
        ),
        patch(
            "oims.model_forge._memory_info",
            return_value=memory_info,
        ),
        patch("oims.model_forge._root_is_read_only", return_value=True),
        patch("oims.model_forge._default_route_present", return_value=False),
        patch("oims.model_forge._network_interfaces", return_value={"lo"}),
        patch(
            "oims.model_forge._forge_mount_policy",
            return_value={
                "plan_read_only": True,
                "base_model_read_only": True,
                "dataset_read_only": True,
                "output_writable": True,
                "output_process_writable": True,
                "tmpfs_active": True,
            },
        ),
        patch(
            "oims.model_forge._cgroup_limits",
            return_value=cgroup_limits,
        ),
        patch("oims.model_forge.os.geteuid", return_value=65532),
        patch("oims.model_forge._container_source_attestation_errors", return_value=()),
        patch("oims.model_forge.subprocess.run") as run,
    ):
        result = inspect_physical_preflight(
            plan,
            accepted_plan_hash=plan["plan_hash"],
            environment=environment,
        )
    assert result["lawful"] is False
    assert expected_error in result["errors"]
    expected_available = memory_info["MemAvailable"] or None
    assert result["sandbox_observation"]["host_memory_available_bytes"] == expected_available
    run.assert_not_called()


def test_probe_requires_process_level_output_write() -> None:
    plan = probe_plan()
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
        "OIMS_FORGE_NVIDIA_RUNTIME_SHA256": "sha256:" + "d" * 64,
        "OIMS_FORGE_NVIDIA_SMI_PATH": TEST_NVIDIA_SMI_PATH,
        "OIMS_FORGE_CONTAINER": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "OIMS_FORGE_BASE_IMAGE": "python:3.12-slim@sha256:" + "a" * 64,
        "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
        "OIMS_FORGE_SOURCE_TREE": "b" * 40,
    }
    with (
        patch(
            "oims.model_forge._proc_status",
            return_value={"CapEff": "0000000000000000", "NoNewPrivs": "1", "Seccomp": "2"},
        ),
        patch(
            "oims.model_forge._memory_info",
            return_value={
                "MemTotal": 128 * 1024**3,
                "MemAvailable": 121 * 1024**3,
                "SwapTotal": 0,
                "SwapFree": 0,
            },
        ),
        patch("oims.model_forge._root_is_read_only", return_value=True),
        patch("oims.model_forge._default_route_present", return_value=False),
        patch("oims.model_forge._network_interfaces", return_value={"lo"}),
        patch(
            "oims.model_forge._forge_mount_policy",
            return_value={
                "plan_read_only": True,
                "base_model_read_only": True,
                "dataset_read_only": True,
                "output_writable": True,
                "output_process_writable": False,
                "tmpfs_active": True,
            },
        ),
        patch(
            "oims.model_forge._cgroup_limits",
            return_value={
                "memory_limit_bytes": 124 * 1024**3,
                "memory_current_bytes": 1 * 1024**3,
                "swap_limit_bytes": 0,
                "pids_limit": 512,
            },
        ),
        patch("oims.model_forge.os.geteuid", return_value=65532),
        patch("oims.model_forge._container_source_attestation_errors", return_value=()),
        patch("oims.model_forge.subprocess.run") as run,
    ):
        result = inspect_physical_preflight(
            plan,
            accepted_plan_hash=plan["plan_hash"],
            environment=environment,
        )
    assert result["lawful"] is False
    assert result["sandbox_observation"]["output_process_writable"] is False
    run.assert_not_called()


@pytest.mark.parametrize(
    "protected_path,observation",
    [
        ("/forge/inputs/base", "base_model_read_only"),
        ("/forge/inputs/dataset", "dataset_read_only"),
    ],
)
def test_probe_mount_policy_rejects_writable_protected_input_submounts(
    protected_path: str,
    observation: str,
) -> None:
    mountinfo = "\n".join(
        [
            "1 0 0:1 / /forge/plan.json ro - ext4 /dev/root ro",
            "2 0 0:2 / /forge/inputs/base ro - ext4 /dev/root ro",
            "3 0 0:3 / /forge/inputs/dataset ro - ext4 /dev/root ro",
            "4 0 0:4 / /forge/output rw - ext4 /dev/root rw",
            "5 0 0:5 / /tmp rw - tmpfs tmpfs rw",
            f"6 2 0:6 / {protected_path}/injected rw - ext4 /dev/root rw",
        ]
    )
    with (
        patch("oims.model_forge.Path.read_text", return_value=mountinfo),
        patch("oims.model_forge._output_path_process_writable", return_value=True),
    ):
        policy = _forge_mount_policy()

    assert policy[observation] is False
    other_observation = (
        "dataset_read_only" if observation == "base_model_read_only" else "base_model_read_only"
    )
    assert policy[other_observation] is True


def test_probe_mount_policy_rejects_writable_protected_input_ancestor() -> None:
    mountinfo = (
        "1 0 0:1 / /forge/plan.json ro - ext4 /dev/root ro\n"
        "2 0 0:2 / /forge/inputs/base ro - ext4 /dev/root ro\n"
        "3 0 0:3 / /forge/inputs/dataset ro - ext4 /dev/root ro\n"
        "4 0 0:4 / /forge/output rw - ext4 /dev/root rw\n"
        "5 0 0:5 / /tmp rw - tmpfs tmpfs rw\n"
        "6 0 0:6 / /forge/inputs rw - ext4 /dev/root rw"
    )
    with (
        patch("oims.model_forge.Path.read_text", return_value=mountinfo),
        patch("oims.model_forge._output_path_process_writable", return_value=True),
    ):
        policy = _forge_mount_policy()

    assert policy["base_model_read_only"] is False
    assert policy["dataset_read_only"] is False


def test_probe_cli_turns_receipt_write_failure_into_a_refusal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = {"lawful": False, "status": "REFUSED", "qmf_admissible": False, "errors": []}
    with (
        patch("oims.cli.inspect_physical_preflight", return_value=result),
        patch("oims.cli.atomic_create_json", side_effect=PermissionError("denied")),
    ):
        exit_code = cli_main(
            [
                "forge",
                "probe",
                "--plan",
                str(PROBE_EXAMPLE),
                "--accept-plan-hash",
                probe_plan()["plan_hash"],
                "--output",
                str(tmp_path),
            ]
        )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["qmf_admissible"] is False
    assert "cannot persist Forge preflight receipt" in payload["errors"][0]


def test_probe_cli_never_replaces_an_existing_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = probe_plan()
    receipt_path = tmp_path / f"preflight-{plan['plan_hash'][7:23]}.json"
    receipt_path.write_text("original evidence\n", encoding="utf-8")
    result = {
        "lawful": True,
        "status": "READY",
        "qmf_admissible": False,
        "errors": [],
        "plan_hash": plan["plan_hash"],
    }
    with patch("oims.cli.inspect_physical_preflight", return_value=result):
        exit_code = cli_main(
            [
                "forge",
                "probe",
                "--plan",
                str(PROBE_EXAMPLE),
                "--accept-plan-hash",
                plan["plan_hash"],
                "--output",
                str(tmp_path),
            ]
        )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert "preflight receipt already exists" in payload["errors"][0]
    assert receipt_path.read_text(encoding="utf-8") == "original evidence\n"


def test_recipe_preserves_reviewed_gpt_oss_moe_targets() -> None:
    plan = load_example()
    recipe = plan["recipe"]
    assert isinstance(recipe, dict)
    parameters = recipe["target_parameters"]
    assert isinstance(parameters, list)
    assert parameters == sorted(parameters)
    assert {value.split(".", 1)[0] for value in parameters} == {"7", "15", "23"}
    assert recipe["target_modules"] == ["all-linear"]
    assert recipe["merge_adapter"] is False
    assert parameters == EXPECTED_TARGET_PARAMETERS

    recipe["target_parameters"] = ["0.mlp.experts.down_proj"]
    rehash(plan)
    assert any("GPT-OSS MoE binding" in error for error in validate_forge_plan(plan))


def test_simulation_duration_output_and_checkpoint_budgets_are_enforced() -> None:
    plan = load_example()
    resources = plan["resources"]
    checkpoints = plan["checkpoints"]
    assert isinstance(resources, dict)
    assert isinstance(checkpoints, dict)
    resources["max_duration_seconds"] = 1
    resources["max_output_bytes"] = 1
    checkpoints["interval_steps"] = 2
    checkpoints["retain_last"] = 1
    rehash(plan)
    errors = validate_forge_plan(plan)
    assert "simulation duration exceeds the resource budget" in errors
    assert "simulation output bytes exceed the resource budget" in errors
    assert "simulation checkpoints.interval_steps must be 1" in errors
    assert "simulation checkpoints.retain_last must preserve the full chain" in errors


def test_simulation_meters_serialized_evidence_before_writing(tmp_path: Path) -> None:
    plan = load_example()
    resources = plan["resources"]
    assert isinstance(resources, dict)
    resources["max_output_bytes"] = 3000
    rehash(plan)
    assert "simulation output bytes exceed the resource budget" not in validate_forge_plan(plan)
    with pytest.raises(ForgePlanError, match="serialized Forge evidence"):
        simulate_forge_run(plan, artifacts_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_simulation_step_count_has_a_global_evidence_bound() -> None:
    plan = load_example()
    resources = plan["resources"]
    simulation = plan["simulation"]
    assert isinstance(resources, dict)
    assert isinstance(simulation, dict)
    resources["max_steps"] = 4097
    simulation["steps"] = 4097
    simulation["synthetic_loss_millionths"] = list(range(4097, 0, -1))
    rehash(plan)
    errors = validate_forge_plan(plan)
    assert "resources.max_steps exceeds 4096" in errors
    assert "simulation steps exceed 4096" in errors


def test_plan_loader_refuses_duplicate_fields_and_non_finite_numbers(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":"1.0.0","schema_version":"1.0.0"}', encoding="utf-8")
    with pytest.raises(ForgePlanError, match="duplicate JSON field"):
        load_forge_plan(duplicate)

    non_finite = tmp_path / "non-finite.json"
    non_finite.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(ForgePlanError, match="non-finite JSON number"):
        load_forge_plan(non_finite)


def test_container_execution_requires_offline_flags_and_immutable_base_image() -> None:
    with patch("oims.model_forge._container_source_attestation_errors", return_value=()):
        errors = forge_container_environment_errors(
            {
                "OIMS_FORGE_CONTAINER": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "OIMS_FORGE_BASE_IMAGE": "python:latest",
                "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
                "OIMS_FORGE_SOURCE_TREE": "b" * 40,
            }
        )
    assert errors == ("OIMS_FORGE_BASE_IMAGE is not pinned by an immutable SHA-256 digest",)


def test_container_source_shortcut_requires_matching_image_attestation() -> None:
    environment = {
        "OIMS_FORGE_CONTAINER": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "OIMS_FORGE_BASE_IMAGE": "python:3.12-slim@sha256:" + "a" * 64,
        "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
        "OIMS_FORGE_SOURCE_TREE": "b" * 40,
    }
    package_digest = "sha256:" + "c" * 64
    with (
        patch(
            "oims.model_forge._read_source_attestation",
            return_value=("a" * 40, "b" * 40, package_digest),
        ),
        patch("oims.model_forge._imported_source_is_isolated", return_value=True),
        patch("oims.model_forge._installed_package_digest", return_value=package_digest),
    ):
        assert forge_container_environment_errors(environment) == ()
    with (
        patch(
            "oims.model_forge._read_source_attestation",
            return_value=("a" * 40, "b" * 40, package_digest),
        ),
        patch("oims.model_forge._imported_source_is_isolated", return_value=False),
    ):
        errors = forge_container_environment_errors(environment)
    assert errors == ("Forge imported source is not isolated from runtime shadowing",)
    with patch(
        "oims.model_forge._read_source_attestation",
        return_value=("c" * 40, "d" * 40, package_digest),
    ):
        errors = forge_container_environment_errors(environment)
    assert errors == ("Forge image source attestation does not match the declared commit and tree",)
    with (
        patch(
            "oims.model_forge._read_source_attestation",
            return_value=("a" * 40, "b" * 40, package_digest),
        ),
        patch("oims.model_forge._imported_source_is_isolated", return_value=True),
        patch(
            "oims.model_forge._installed_package_digest",
            return_value="sha256:" + "d" * 64,
        ),
    ):
        errors = forge_container_environment_errors(environment)
    assert errors == ("Forge imported package does not match the build attestation",)


def test_preimport_entrypoint_rejects_installed_package_tampering(tmp_path: Path) -> None:
    package_root = tmp_path / "oims"
    package_root.mkdir()
    (package_root / "__init__.py").write_text("VERSION = 1\n", encoding="utf-8")
    (package_root / "model_forge.py").write_text("LAWFUL = True\n", encoding="utf-8")
    observed = entrypoint_package_digest(package_root)
    assert observed is not None
    assert _installed_package_digest(package_root) == observed
    attestation = tmp_path / "source.attestation"
    attestation.write_text(
        f"commit={'a' * 40}\ntree={'b' * 40}\npackage_sha256={observed}\n",
        encoding="ascii",
    )
    assert verify_installed_package(attestation, package_root, (Path("/"),)) == ()
    (package_root / "model_forge.py").write_text("LAWFUL = False\n", encoding="utf-8")
    assert verify_installed_package(attestation, package_root, (Path("/"),)) == (
        "Forge installed package does not match its build attestation",
    )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO inputs require POSIX")
def test_preimport_attestation_reader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    attestation = tmp_path / "source.attestation"
    os.mkfifo(attestation)

    assert forge_entrypoint._read_values(attestation) is None
    assert model_forge_module._read_source_attestation(attestation) is None


def test_preimport_entrypoint_rejects_matching_replacement_mounts(tmp_path: Path) -> None:
    package_root = tmp_path / "oims"
    package_root.mkdir()
    package_file = package_root / "model_forge.py"
    package_file.write_text("LAWFUL = False\n", encoding="utf-8")
    observed = entrypoint_package_digest(package_root)
    assert observed is not None
    attestation = tmp_path / "source.attestation"
    attestation.write_text(
        f"commit={'a' * 40}\ntree={'b' * 40}\npackage_sha256={observed}\n",
        encoding="ascii",
    )
    assert verify_installed_package(
        attestation,
        package_root,
        (Path("/"), package_file, attestation),
    ) == ("Forge protected executable runtime contains an unexpected mount",)


def test_preimport_entrypoint_rejects_dependency_mounts(tmp_path: Path) -> None:
    interpreter_prefix = tmp_path / "python"
    site_packages = interpreter_prefix / "lib" / "site-packages"
    package_root = site_packages / "oims"
    dependency_root = site_packages / "yaml"
    package_root.mkdir(parents=True)
    dependency_root.mkdir()
    attestation = interpreter_prefix / "share" / "source.attestation"
    attestation.parent.mkdir()
    attestation.write_text("attestation\n", encoding="ascii")
    verifier = interpreter_prefix / "libexec" / "entrypoint.py"
    verifier.parent.mkdir()
    verifier.write_text("verifier\n", encoding="utf-8")
    errors = protected_mount_errors(
        package_root,
        attestation,
        verifier,
        (Path("/"), dependency_root),
        interpreter_prefix,
    )
    assert errors == ("Forge protected executable runtime contains an unexpected mount",)


def test_preimport_entrypoint_rejects_native_library_mounts(tmp_path: Path) -> None:
    interpreter_prefix = tmp_path / "python"
    package_root = interpreter_prefix / "lib" / "site-packages" / "oims"
    package_root.mkdir(parents=True)
    attestation = interpreter_prefix / "share" / "source.attestation"
    attestation.parent.mkdir()
    attestation.write_text("attestation\n", encoding="ascii")
    verifier = interpreter_prefix / "libexec" / "entrypoint.py"
    verifier.parent.mkdir()
    verifier.write_text("verifier\n", encoding="utf-8")
    native_library = Path("/lib/x86_64-linux-gnu/libc.so.6")

    errors = protected_mount_errors(
        package_root,
        attestation,
        verifier,
        (Path("/"), native_library),
        interpreter_prefix,
        (native_library,),
    )

    assert errors == ("Forge protected executable runtime contains an unexpected mount",)


def test_preimport_entrypoint_allows_attested_nvidia_runtime_mounts(tmp_path: Path) -> None:
    interpreter_prefix = tmp_path / "python"
    package_root = interpreter_prefix / "lib" / "site-packages" / "oims"
    package_root.mkdir(parents=True)
    attestation = interpreter_prefix / "share" / "source.attestation"
    attestation.parent.mkdir()
    attestation.write_text("attestation\n", encoding="ascii")
    verifier = interpreter_prefix / "libexec" / "entrypoint.py"
    verifier.parent.mkdir()
    verifier.write_text("verifier\n", encoding="utf-8")
    runtime_root = Path("/usr/bin")
    nvidia_smi = runtime_root / "nvidia-smi"

    errors = protected_mount_errors(
        package_root,
        attestation,
        verifier,
        (Path("/"), nvidia_smi),
        interpreter_prefix,
        (runtime_root,),
        (runtime_root,),
        (nvidia_smi,),
    )

    assert errors == ()


@pytest.mark.parametrize("target", forge_entrypoint.PROBE_OBSERVATION_PATHS)
def test_preimport_probe_rejects_mounts_over_observation_sources(target: Path) -> None:
    baseline = (
        forge_entrypoint.MountRecord(Path("/"), frozenset({"rw"}), "overlay", "overlay", Path("/")),
        forge_entrypoint.MountRecord(Path("/proc"), frozenset({"rw"}), "proc", "proc", Path("/")),
        forge_entrypoint.MountRecord(Path("/sys"), frozenset({"ro"}), "sysfs", "sysfs", Path("/")),
        forge_entrypoint.MountRecord(
            Path("/sys/fs/cgroup"),
            frozenset({"ro"}),
            "cgroup2",
            "cgroup",
            Path("/"),
        ),
    )
    injected = forge_entrypoint.MountRecord(
        target,
        frozenset({"ro"}),
        "ext4",
        "/attacker/forged-observation",
        Path("/attacker/forged-observation"),
    )

    errors = forge_entrypoint.probe_observation_mount_errors((*baseline, injected), "/")

    assert errors
    assert errors[0].startswith("Forge physical-preflight observation")


def test_preimport_mountinfo_parser_preserves_cgroup_root() -> None:
    mountinfo = b"117 116 0:24 /attacker\\040subgroup /sys/fs/cgroup ro - cgroup2 cgroup rw\n"

    with patch.object(forge_entrypoint, "_read_proc_metadata", return_value=mountinfo):
        records = forge_entrypoint._mount_records()

    assert records is not None
    assert records[0].root == Path("/attacker subgroup")


@pytest.mark.parametrize(
    ("mount_root", "membership"),
    [
        (Path("/attacker/subgroup"), "/"),
        (Path("/"), "/attacker/subgroup"),
    ],
)
def test_preimport_probe_rejects_cgroup_subgroup_substitution(
    mount_root: Path,
    membership: str,
) -> None:
    records = (
        forge_entrypoint.MountRecord(Path("/"), frozenset({"rw"}), "overlay", "overlay", Path("/")),
        forge_entrypoint.MountRecord(Path("/proc"), frozenset({"rw"}), "proc", "proc", Path("/")),
        forge_entrypoint.MountRecord(Path("/sys"), frozenset({"ro"}), "sysfs", "sysfs", Path("/")),
        forge_entrypoint.MountRecord(
            Path("/sys/fs/cgroup"),
            frozenset({"ro"}),
            "cgroup2",
            "cgroup",
            mount_root,
        ),
    )

    errors = forge_entrypoint.probe_observation_mount_errors(records, membership)

    assert errors
    assert errors[0].startswith("Forge physical-preflight")


def test_nvidia_runtime_mount_attestation_hashes_read_only_regular_files(
    tmp_path: Path,
) -> None:
    runtime_file = tmp_path / "nvidia-smi"
    runtime_bytes = b"attested NVIDIA runtime fixture\n"
    runtime_file.write_bytes(runtime_bytes)
    approvals = tmp_path / "nvidia-runtime.approved"
    approvals.write_text(
        f"{runtime_file}=sha256:{hashlib.sha256(runtime_bytes).hexdigest()}\n",
        encoding="ascii",
    )
    records = ((runtime_file, frozenset({"ro"})),)

    with patch.object(forge_entrypoint, "_is_nvidia_runtime_path", return_value=True):
        attestation = forge_entrypoint.nvidia_runtime_mount_attestation(records, approvals)

    assert attestation is not None
    assert attestation[0] == (runtime_file,)
    assert attestation[1].startswith("sha256:")
    assert len(attestation[1]) == 71


def test_nvidia_runtime_mount_attestation_rejects_unapproved_bytes(tmp_path: Path) -> None:
    runtime_file = tmp_path / "nvidia-smi"
    runtime_file.write_bytes(b"attacker supplied executable\n")
    approvals = tmp_path / "nvidia-runtime.approved"
    trusted_digest = hashlib.sha256(b"trusted NVIDIA executable\n").hexdigest()
    approvals.write_text(f"{runtime_file}=sha256:{trusted_digest}\n", encoding="ascii")
    records = ((runtime_file, frozenset({"ro"})),)

    with patch.object(forge_entrypoint, "_is_nvidia_runtime_path", return_value=True):
        assert forge_entrypoint.nvidia_runtime_mount_attestation(records, approvals) is None


@pytest.mark.parametrize(
    "executable",
    [
        "nvidia-smi",
        "nvidia-debugdump",
        "nvidia-persistenced",
        "nvidia-cuda-mps-control",
        "nvidia-cuda-mps-server",
    ],
)
def test_nvidia_toolkit_utility_executable_set_is_bounded_and_complete(executable: str) -> None:
    assert forge_entrypoint._is_nvidia_runtime_path(Path("/usr/bin") / executable)
    assert not forge_entrypoint._is_nvidia_runtime_path(Path("/usr/bin/nvidia-unreviewed"))


def test_preimport_probe_passes_nvidia_attestation_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = "sha256:" + "e" * 64
    records = ((Path("/usr/bin/nvidia-smi"), frozenset({"ro"})),)
    monkeypatch.delenv("OIMS_FORGE_NVIDIA_RUNTIME_SHA256", raising=False)
    monkeypatch.setenv("OIMS_FORGE_NVIDIA_SMI_PATH", "/forge/inputs/base/nvidia-smi")

    with (
        patch.object(forge_entrypoint, "_mount_records", return_value=records),
        patch.object(
            forge_entrypoint,
            "nvidia_runtime_mount_attestation",
            return_value=((records[0][0],), digest),
        ),
        patch.object(forge_entrypoint, "verify_installed_package", return_value=()),
        patch.object(forge_entrypoint.os, "execv", side_effect=OSError("exec intercepted")),
        pytest.raises(OSError, match="exec intercepted"),
    ):
        forge_entrypoint.main(["forge", "probe"])

    assert os.environ["OIMS_FORGE_NVIDIA_RUNTIME_SHA256"] == digest
    assert os.environ["OIMS_FORGE_NVIDIA_SMI_PATH"] == "/usr/bin/nvidia-smi"


def test_oci_boundary_is_offline_unprivileged_and_non_training() -> None:
    compose = yaml.safe_load((ROOT / "forge" / "compose.yaml").read_text(encoding="utf-8"))
    for service_name in ("simulate", "verify", "probe"):
        service = compose["services"][service_name]
        assert service["network_mode"] == "none"
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["mem_limit"] == service["memswap_limit"]
        assert service["build"]["context"].startswith("${FORGE_BUILD_CONTEXT:")
        assert service["environment"]["OIMS_FORGE_BASE_IMAGE"].startswith("${FORGE_BASE_IMAGE:")
        assert service["environment"]["OIMS_FORGE_SOURCE_COMMIT"].startswith(
            "${FORGE_SOURCE_COMMIT:"
        )
        assert service["environment"]["OIMS_FORGE_SOURCE_TREE"].startswith("${FORGE_SOURCE_TREE:")
        assert all(
            volume.get("read_only") is True
            for volume in service["volumes"]
            if volume["target"] != "/forge/output"
        )
        command = " ".join(str(item) for item in service["command"])
        assert " train " not in f" {command} "
        assert command.startswith(("forge simulate", "forge verify", "forge probe"))

    assert compose["services"]["verify"]["command"] == [
        "forge",
        "verify",
        "--receipt",
        "${FORGE_RECEIPT:-/forge/output/receipt.json}",
    ]

    probe = compose["services"]["probe"]
    device = probe["deploy"]["resources"]["reservations"]["devices"][0]
    assert device["capabilities"] == ["gpu"]
    assert device["device_ids"] == ["${FORGE_GPU_DEVICE_ID:-0}"]

    containerfile = (ROOT / "forge" / "Containerfile").read_text(encoding="utf-8")
    assert "ARG FORGE_BASE_IMAGE\nFROM ${FORGE_BASE_IMAGE}" in containerfile
    assert "FROM python:" not in containerfile
    assert "source.attestation" in containerfile
    assert "WORKDIR /workspace" not in containerfile
    assert "rm -rf /opt/oims-forge-build" in containerfile
    assert "WORKDIR /forge" in containerfile
    assert "--no-compile" in containerfile
    assert "--seal-attestation" in containerfile
    assert (
        'ENTRYPOINT ["python", "-I", "/usr/local/libexec/oims-forge-entrypoint.py"]'
        in containerfile
    )
    entrypoint = (ROOT / "forge" / "oims_forge_entrypoint.py").read_text(encoding="utf-8")
    assert "/proc/self/mountinfo" in entrypoint
    assert "/proc/self/maps" in entrypoint
    assert "NATIVE_RUNTIME_ROOTS" in entrypoint
    assert "nvidia_runtime_mount_attestation" in entrypoint
    assert "nvidia_runtime_approvals" in entrypoint
    assert "OIMS_FORGE_NVIDIA_RUNTIME_SHA256" in entrypoint
    assert "OIMS_FORGE_NVIDIA_SMI_PATH" in entrypoint
    assert "protected executable runtime contains an unexpected mount" in entrypoint
    assert "nvidia-runtime.approved" in containerfile
    launcher = (ROOT / "scripts" / "run_model_forge.ps1").read_text(encoding="utf-8")
    assert "status --porcelain=v1 --untracked-files=all" in launcher
    assert "ls-files -v" in launcher
    assert "archive --format=tar" in launcher
    assert "$env:FORGE_BUILD_CONTEXT = $BuildContext" in launcher
    assert "Model Forge refuses a dirty build context" in launcher
    assert "repository-affecting Git environment overrides" in launcher
    assert "GIT_DIR" in launcher
    assert "GIT_WORK_TREE" in launcher
    assert "rev-parse --show-toplevel" in launcher
    assert "Git did not resolve the expected Model Forge worktree" in launcher
    assert "SourceCommit does not match the repository HEAD" in launcher
    assert "$env:FORGE_SOURCE_TREE = $SourceTree" in launcher
    assert "'Validate', 'Simulate', 'Verify', 'Probe'" in launcher
    assert "Verify requires -Receipt" in launcher
    assert "Verify requires Receipt to remain beneath OutputDir" in launcher
    assert "$env:FORGE_RECEIPT = $ContainerReceipt" in launcher
    assert "run --rm --build verify" in launcher
    runtime_lock = (ROOT / "requirements" / "forge-runtime.lock").read_text(encoding="utf-8")
    assert "torch" not in runtime_lock.lower()
    assert "transformers" not in runtime_lock.lower()
    assert "peft" not in runtime_lock.lower()


def test_forge_receipt_schemas_refuse_undeclared_fields_and_match_runtime(tmp_path: Path) -> None:
    run_schema = json.loads(
        (ROOT / "schemas" / "model-forge-run-receipt.schema.json").read_text(encoding="utf-8")
    )
    run_receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    assert run_schema["additionalProperties"] is False
    assert set(run_schema["required"]) == set(run_schema["properties"])
    assert set(run_receipt) == set(run_schema["properties"])

    preflight_schema = json.loads(
        (ROOT / "schemas" / "model-forge-preflight-receipt.schema.json").read_text(encoding="utf-8")
    )
    plan = probe_plan()
    preflight_receipt = inspect_physical_preflight(
        plan,
        accepted_plan_hash="sha256:" + "0" * 64,
        environment={},
    )
    assert preflight_schema["additionalProperties"] is False
    assert set(preflight_schema["required"]) == set(preflight_schema["properties"])
    assert set(preflight_receipt) == set(preflight_schema["properties"])
