from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from oims.cli import main as cli_main
from oims.manifest import ROOT
from oims.model_forge import (
    EXPECTED_TARGET_PARAMETERS,
    ForgePlanError,
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


def test_simulation_refuses_to_overwrite_an_existing_run(tmp_path: Path) -> None:
    plan = load_example()
    simulate_forge_run(plan, artifacts_dir=tmp_path)
    with pytest.raises(ForgePlanError, match="already exists"):
        simulate_forge_run(plan, artifacts_dir=tmp_path)


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


def test_telemetry_tampering_breaks_verification(tmp_path: Path) -> None:
    receipt = simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    run_dir = tmp_path / receipt["run_id"]
    telemetry = run_dir / "telemetry.jsonl"
    telemetry.write_text(telemetry.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
    result = verify_forge_run(run_dir / "receipt.json")
    assert result["valid"] is False
    assert "Forge telemetry hash is invalid" in result["errors"]


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


def test_probe_requires_exact_dual_unlock_before_device_inspection() -> None:
    plan = probe_plan()
    with (
        patch("oims.model_forge.current_git_commit", return_value="a" * 40),
        patch("oims.model_forge.subprocess.run") as run,
    ):
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


def test_probe_can_prove_a_locked_4090_sandbox_without_training() -> None:
    plan = probe_plan()
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
        "OIMS_FORGE_CONTAINER": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "OIMS_FORGE_BASE_IMAGE": "python:3.12-slim@sha256:" + "a" * 64,
        "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
        "OIMS_FORGE_SOURCE_TREE": "b" * 40,
    }
    completed = subprocess.CompletedProcess(
        args=["nvidia-smi"],
        returncode=0,
        stdout=(
            "GPU-00000000-0000-0000-0000-000000000000, NVIDIA GeForce RTX 4090, "
            "24564, 0, 42, 20, 450\n"
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
        patch("oims.model_forge.current_git_commit", return_value="a" * 40),
        patch("oims.model_forge.subprocess.run", return_value=completed) as run,
    ):
        result = inspect_physical_preflight(
            plan,
            accepted_plan_hash=plan["plan_hash"],
            environment=environment,
        )
    assert result["lawful"] is True
    assert result["status"] == "READY"
    assert result["gpu"]["name"] == "NVIDIA GeForce RTX 4090"
    assert result["sandbox_observation"]["host_memory_available_bytes"] == 121 * 1024**3
    assert result["training_started"] is False
    assert result["qmf_admissible"] is False
    run.assert_called_once()


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


def test_direct_simulation_refuses_dirty_source_before_writing(tmp_path: Path) -> None:
    dirty = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout=" M oims/model_forge.py\n",
        stderr="",
    )
    with (
        patch.dict(
            "oims.model_forge.os.environ",
            {
                "OIMS_FORGE_CONTAINER": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "OIMS_FORGE_BASE_IMAGE": "python:3.12-slim@sha256:" + "a" * 64,
                "OIMS_FORGE_SOURCE_COMMIT": "a" * 40,
                "OIMS_FORGE_SOURCE_TREE": "b" * 40,
            },
            clear=True,
        ),
        patch("oims.model_forge.subprocess.run", return_value=dirty),
        pytest.raises(ForgePlanError, match="clean Git working tree"),
    ):
        simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_direct_simulation_refuses_index_hidden_source_changes(tmp_path: Path) -> None:
    clean_status = subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=0,
        stdout="",
        stderr="",
    )
    hidden_index = subprocess.CompletedProcess(
        args=["git", "ls-files"],
        returncode=0,
        stdout="h oims/model_forge.py\0",
        stderr="",
    )
    with (
        patch.dict("oims.model_forge.os.environ", {}, clear=True),
        patch("oims.model_forge.subprocess.run", side_effect=[clean_status, hidden_index]),
        pytest.raises(ForgePlanError, match="clean Git working tree"),
    ):
        simulate_forge_run(load_example(), artifacts_dir=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    ("memory_info", "cgroup_limits", "expected_error"),
    [
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
            "available container memory is below the plan's host-memory ceiling",
        ),
    ],
)
def test_probe_requires_current_memory_headroom(
    memory_info: dict[str, int],
    cgroup_limits: dict[str, int],
    expected_error: str,
) -> None:
    plan = probe_plan()
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
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
        patch("oims.model_forge.current_git_commit", return_value="a" * 40),
        patch("oims.model_forge.subprocess.run") as run,
    ):
        result = inspect_physical_preflight(
            plan,
            accepted_plan_hash=plan["plan_hash"],
            environment=environment,
        )
    assert result["lawful"] is False
    assert expected_error in result["errors"]
    run.assert_not_called()


def test_probe_requires_process_level_output_write() -> None:
    plan = probe_plan()
    environment = {
        "OIMS_FORGE_ENABLE_PROBE": "1",
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
        patch("oims.model_forge.current_git_commit", return_value="a" * 40),
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


def test_probe_cli_turns_receipt_write_failure_into_a_refusal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = {"lawful": False, "status": "REFUSED", "qmf_admissible": False, "errors": []}
    with (
        patch("oims.cli.inspect_physical_preflight", return_value=result),
        patch("oims.cli.atomic_write_json", side_effect=PermissionError("denied")),
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
    with patch(
        "oims.model_forge._read_source_attestation",
        return_value=("a" * 40, "b" * 40),
    ):
        assert forge_container_environment_errors(environment) == ()
    with patch(
        "oims.model_forge._read_source_attestation",
        return_value=("c" * 40, "d" * 40),
    ):
        errors = forge_container_environment_errors(environment)
    assert errors == ("Forge image source attestation does not match the declared commit and tree",)


def test_oci_boundary_is_offline_unprivileged_and_non_training() -> None:
    compose = yaml.safe_load((ROOT / "forge" / "compose.yaml").read_text(encoding="utf-8"))
    for service_name in ("simulate", "probe"):
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
        assert command.startswith(("forge simulate", "forge probe"))

    probe = compose["services"]["probe"]
    device = probe["deploy"]["resources"]["reservations"]["devices"][0]
    assert device["capabilities"] == ["gpu"]
    assert device["device_ids"] == ["${FORGE_GPU_DEVICE_ID:-0}"]

    containerfile = (ROOT / "forge" / "Containerfile").read_text(encoding="utf-8")
    assert "ARG FORGE_BASE_IMAGE\nFROM ${FORGE_BASE_IMAGE}" in containerfile
    assert "FROM python:" not in containerfile
    assert "source.attestation" in containerfile
    launcher = (ROOT / "scripts" / "run_model_forge.ps1").read_text(encoding="utf-8")
    assert "status --porcelain=v1 --untracked-files=all" in launcher
    assert "ls-files -v" in launcher
    assert "archive --format=tar" in launcher
    assert "$env:FORGE_BUILD_CONTEXT = $BuildContext" in launcher
    assert "Model Forge refuses a dirty build context" in launcher
    assert "SourceCommit does not match the repository HEAD" in launcher
    assert "$env:FORGE_SOURCE_TREE = $SourceTree" in launcher
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
    with patch("oims.model_forge.current_git_commit", return_value="a" * 40):
        preflight_receipt = inspect_physical_preflight(
            plan,
            accepted_plan_hash="sha256:" + "0" * 64,
            environment={},
        )
    assert preflight_schema["additionalProperties"] is False
    assert set(preflight_schema["required"]) == set(preflight_schema["properties"])
    assert set(preflight_receipt) == set(preflight_schema["properties"])
