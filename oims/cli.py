"""Command-line interface for model download, verification, and execution."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from .agents import load_agent_registry
from .backends import DeterministicFixtureBackend, LlamaCppBackend
from .collective import run_collective_request
from .doctor import run_diagnostics
from .manifest import load_manifest
from .runtime import print_json, run_family, run_tier
from .verify import verify_artifact_file
from .weights import inspect_tier, pull_weights, selected_tiers


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oims")
    parser.add_argument(
        "--weights-dir",
        type=_path,
        default=_path(os.environ.get("OIMS_WEIGHTS_DIR", "weights")),
        help="local weight root (default: ./weights or OIMS_WEIGHTS_DIR)",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=_path,
        default=_path(os.environ.get("OIMS_ARTIFACTS_DIR", "artifacts")),
        help="conformance output directory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="check disk, weights, llama.cpp, and GPU readiness")
    subparsers.add_parser("agents", help="list declared CollectiveOS role bindings")

    weights = subparsers.add_parser("weights", help="manage pinned GGUF files")
    weights.add_argument("action", choices=("pull", "check"))
    weights.add_argument("--tier", default="all", help="ISO-1B, ISO-7B, ISO-30B, or all")
    weights.add_argument(
        "--full-hash",
        action="store_true",
        help="rehash every local GGUF file during check",
    )

    run = subparsers.add_parser("run", help="run one model tier")
    run.add_argument("--tier", required=True)
    run.add_argument("--prompt", required=True)
    run.add_argument("--max-tokens", type=int, default=256)
    run.add_argument("--backend", choices=("weights", "fixture"), default="weights")
    run.add_argument("--n-gpu-layers", type=int, default=None)
    run.add_argument("--n-ctx", type=int, default=None)

    for command, help_text in (
        ("family", "run all heterogeneous tiers sequentially"),
        ("mesh", "run the explicit ISO-Mesh conformance surface"),
    ):
        family = subparsers.add_parser(command, help=help_text)
        family.add_argument("--prompt", required=True)
        family.add_argument("--max-tokens", type=int, default=256)
        family.add_argument("--backend", choices=("weights", "fixture"), default="weights")
        family.add_argument("--n-gpu-layers", type=int, default=None)
        family.add_argument("--n-ctx", type=int, default=None)

    collective = subparsers.add_parser(
        "collective",
        help="run a governed CollectiveOS agent-role request",
    )
    collective.add_argument("--request-file", type=_path)
    collective.add_argument("--agent")
    collective.add_argument("--prompt")
    collective.add_argument("--max-tokens", type=int, default=256)
    collective.add_argument("--backend", choices=("weights", "fixture"), default="weights")
    collective.add_argument("--n-gpu-layers", type=int, default=None)
    collective.add_argument("--n-ctx", type=int, default=None)

    verify = subparsers.add_parser("verify", help="verify a sealed OIMS artifact")
    verify.add_argument("--path", type=_path, required=True)
    verify.add_argument(
        "--require-weight-backed",
        action="store_true",
        help="also require WEIGHT_BACKED family evidence",
    )
    return parser


def _backend_factory(args: argparse.Namespace):
    if args.backend == "fixture":
        return lambda spec: DeterministicFixtureBackend(spec)
    return lambda spec: LlamaCppBackend(
        spec,
        weights_root=args.weights_dir,
        n_gpu_layers=args.n_gpu_layers,
        n_ctx=args.n_ctx,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest()
    if args.command == "doctor":
        result = run_diagnostics(manifest, args.weights_dir)
        print_json(result)
        return 0 if result["ready_for_family_run"] else 2
    if args.command == "agents":
        registry = load_agent_registry(manifest=manifest)
        print_json(
            {
                "family": registry.family,
                "activation_semantics": registry.activation_semantics,
                "autonomous_worker_claim": registry.autonomous_worker_claim,
                "governance_route": list(registry.governance_route),
                "agent_manifest_sha256": registry.source_hash,
                "default_agent": registry.default_agent,
                "profiles": [profile.to_mapping() for profile in registry.profiles],
            }
        )
        return 0
    if args.command == "weights":
        specs = selected_tiers(manifest, args.tier)
        if args.action == "pull":
            print_json({"weights": pull_weights(specs, args.weights_dir)})
            return 0
        statuses = [
            inspect_tier(spec, args.weights_dir, compute_hashes=args.full_hash) for spec in specs
        ]
        print_json({"weights": statuses})
        ready = all(
            item["lock_matches_manifest"]
            and item["size_verified"]
            and (item["hash_verified"] if args.full_hash else True)
            for item in statuses
        )
        return 0 if ready else 2
    if args.command == "verify":
        result = verify_artifact_file(args.path)
        if args.require_weight_backed and result.get("evidence_class") != "WEIGHT_BACKED":
            result["valid"] = False
            result["errors"].append("artifact is not WEIGHT_BACKED")
        print_json(result)
        return 0 if result["valid"] else 2
    if args.command == "collective":
        if args.request_file:
            try:
                request = json.loads(args.request_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SystemExit(f"cannot load CollectiveOS request: {exc}") from exc
        else:
            if args.prompt is None:
                raise SystemExit("collective requires --prompt or --request-file")
            request = {"prompt": args.prompt, "max_tokens": args.max_tokens}
            if args.agent is not None:
                request["agent"] = args.agent
        if args.backend == "fixture":
            profile_factory = lambda spec, profile: DeterministicFixtureBackend(spec)
        else:
            profile_factory = lambda spec, profile: LlamaCppBackend(
                spec,
                weights_root=args.weights_dir,
                n_gpu_layers=args.n_gpu_layers,
                n_ctx=args.n_ctx,
                system_prompt=profile.system_prompt,
            )
        result = run_collective_request(
            request,
            manifest=manifest,
            backend_factory=profile_factory,
            weights_dir=args.weights_dir,
            artifacts_dir=args.artifacts_dir,
        )
        print_json(result)
        return 0 if result["result"].get("lawful", False) else 1

    factory = _backend_factory(args)
    if args.command == "run":
        result = run_tier(
            args.tier,
            args.prompt,
            manifest=manifest,
            backend_factory=factory,
            weights_dir=args.weights_dir,
            artifacts_dir=args.artifacts_dir,
            max_tokens=args.max_tokens,
        )
    else:
        result = run_family(
            args.prompt,
            manifest=manifest,
            backend_factory=factory,
            weights_dir=args.weights_dir,
            artifacts_dir=args.artifacts_dir,
            max_tokens=args.max_tokens,
        )
    print_json(result)
    return 0 if result.get("lawful", result.get("runtime_isomorphic", False)) else 1
