"""Target-machine readiness diagnostics."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from .backends import llama_cpp_version_supported
from .manifest import FamilyManifest
from .weights import inspect_tier


def run_diagnostics(manifest: FamilyManifest, weights_root: Path) -> dict[str, Any]:
    probe_path = weights_root
    while not probe_path.exists() and probe_path != probe_path.parent:
        probe_path = probe_path.parent
    disk = shutil.disk_usage(probe_path)
    required = sum(tier.download_bytes for tier in manifest.tiers)

    llama_installed = False
    gpu_offload_supported: bool | None = None
    llama_version: str | None = None
    runtime_version_ready = False
    try:
        import llama_cpp

        llama_installed = True
        llama_version = getattr(llama_cpp, "__version__", "unknown")
        runtime_version_ready = llama_cpp_version_supported(llama_version)
        support_probe = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        if callable(support_probe):
            gpu_offload_supported = bool(support_probe())
    except ImportError:
        pass

    weights = [inspect_tier(tier, weights_root, compute_hashes=False) for tier in manifest.tiers]
    weights_ready = all(item["size_verified"] and item["lock_matches_manifest"] for item in weights)
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "weights_root": str(weights_root),
        "disk_free_bytes": disk.free,
        "download_bytes": required,
        "disk_ready": disk.free >= required,
        "llama_cpp_installed": llama_installed,
        "llama_cpp_version": llama_version,
        "runtime_version_ready": runtime_version_ready,
        "gpu_offload_supported": gpu_offload_supported,
        "weights_ready": weights_ready,
        "tiers": weights,
        "ready_for_family_run": bool(
            llama_installed
            and runtime_version_ready
            and weights_ready
            and gpu_offload_supported is not False
        ),
    }
