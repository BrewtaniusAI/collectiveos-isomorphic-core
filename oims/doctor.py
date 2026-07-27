"""Target-machine readiness diagnostics."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from .manifest import FamilyManifest
from .weights import inspect_tier


def run_diagnostics(manifest: FamilyManifest, weights_root: Path) -> dict[str, Any]:
    probe_path = weights_root
    while not probe_path.exists() and probe_path != probe_path.parent:
        probe_path = probe_path.parent
    disk = shutil.disk_usage(probe_path)
    required = sum(tier.download_bytes_approx for tier in manifest.tiers)

    llama_installed = False
    gpu_offload_supported: bool | None = None
    llama_version: str | None = None
    try:
        import llama_cpp

        llama_installed = True
        llama_version = getattr(llama_cpp, "__version__", "unknown")
        support_probe = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        if callable(support_probe):
            gpu_offload_supported = bool(support_probe())
    except ImportError:
        pass

    weights = [inspect_tier(tier, weights_root, compute_hashes=False) for tier in manifest.tiers]
    weights_ready = all(item["size_verified"] for item in weights)
    return {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "weights_root": str(weights_root),
        "disk_free_bytes": disk.free,
        "download_bytes_approx": required,
        "disk_ready": disk.free >= required,
        "llama_cpp_installed": llama_installed,
        "llama_cpp_version": llama_version,
        "gpu_offload_supported": gpu_offload_supported,
        "weights_ready": weights_ready,
        "tiers": weights,
        "ready_for_family_run": bool(
            llama_installed and weights_ready and gpu_offload_supported is not False
        ),
    }
