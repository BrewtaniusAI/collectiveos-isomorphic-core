"""Command-line interface for model download, verification, and execution."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from pathlib import Path

from .backends import DeterministicFixtureBackend, LlamaCppBackend
from .doctor import run_diagnostics
from .manifest import load_manifest
from .runtime import print_json, run_family, run_tier
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

    family = subparsers.add_parser("family", help="run all tiers sequentially")
    family.add_argument("--prompt", required=True)
    family.add_argument("--max-tokens", type=int, default=256)
    family.add_argument("--backend", choices=("weights", "fixture"), default="weights")
    family.add_argument("--n-gpu-layers", type=int, default=None)
    family.add_argument("--n-ctx", type=int, default=None)
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
    if args.command == "weights":
        specs = selected_tiers(manifest, args.tier)
        if args.action == "pull":
            print_json({"weights": pull_weights(specs, args.weights_dir)})
            return 0
        statuses = [
            inspect_tier(spec, args.weights_dir, compute_hashes=args.full_hash) for spec in specs
        ]
        print_json({"weights": statuses})
        check_field = "hash_verified" if args.full_hash else "size_verified"
        return 0 if all(item[check_field] for item in statuses) else 2

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
