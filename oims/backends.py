"""Inference backends for pinned local GGUF weights."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .manifest import TierSpec

SYSTEM_PROMPT = """You are an OIMS governed intelligence tier.
Answer the user's request directly and accurately.
Do not claim evidence you do not possess.
If the request cannot be answered lawfully, explain the boundary instead of inventing facts."""


class BackendError(RuntimeError):
    """Raised when real model weights cannot be loaded or executed."""


@dataclass(frozen=True)
class BackendResult:
    output: str
    backend: str
    real_weights: bool
    elapsed_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)


class InferenceBackend(Protocol):
    name: str
    real_weights: bool

    def generate(self, prompt: str, *, max_tokens: int) -> BackendResult: ...

    def close(self) -> None: ...


def resolve_weight_files(spec: TierSpec, weights_root: Path) -> tuple[Path, ...]:
    tier_dir = weights_root / spec.name
    resolved = tuple(tier_dir / filename for filename in spec.files)
    missing = [str(path) for path in resolved if not path.is_file()]
    if missing:
        raise BackendError(
            f"{spec.name} weights are incomplete. Missing: {', '.join(missing)}. "
            f"Run: python -m oims weights pull --tier {spec.name}"
        )
    return resolved


class LlamaCppBackend:
    """Load one pinned GGUF tier with llama-cpp-python."""

    name = "llama-cpp-python"
    real_weights = True

    def __init__(
        self,
        spec: TierSpec,
        *,
        weights_root: Path,
        n_gpu_layers: int | None = None,
        n_ctx: int | None = None,
        seed: int = 3407,
    ) -> None:
        from .weights import inspect_tier

        try:
            weight_status = inspect_tier(spec, weights_root, compute_hashes=True)
        except OSError as exc:
            raise BackendError(f"{spec.name} weight verification failed: {exc}") from exc
        if not weight_status["complete"]:
            resolve_weight_files(spec, weights_root)
        if not weight_status["hash_verified"]:
            raise BackendError(
                f"{spec.name} weight hashes do not match its local lock. "
                f"Run: python -m oims weights pull --tier {spec.name}"
            )
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise BackendError(
                "llama-cpp-python is not installed. Install the CUDA-enabled build "
                "described in WEIGHTS.md."
            ) from exc

        files = resolve_weight_files(spec, weights_root)
        self.spec = spec
        self.files = files
        self.weight_status = weight_status
        try:
            self._model = Llama(
                model_path=str(files[0]),
                n_ctx=n_ctx or spec.context_length,
                n_gpu_layers=spec.gpu_layers if n_gpu_layers is None else n_gpu_layers,
                seed=seed,
                verbose=False,
            )
        except Exception as exc:
            raise BackendError(f"{spec.name} failed to load with llama.cpp: {exc}") from exc

    def generate(self, prompt: str, *, max_tokens: int) -> BackendResult:
        started = time.perf_counter()
        try:
            response = self._model.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                top_p=1.0,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise BackendError(f"{self.spec.name} inference failed: {exc}") from exc
        try:
            output = str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise BackendError(f"unexpected llama.cpp response structure: {response!r}") from exc
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        return BackendResult(
            output=output,
            backend=self.name,
            real_weights=True,
            elapsed_ms=elapsed_ms,
            metadata={
                "model_file": self.files[0].name,
                "split_files": len(self.files),
                "weight_hash_verified": True,
                "usage": usage,
            },
        )

    def close(self) -> None:
        close = getattr(self._model, "close", None)
        if callable(close):
            close()


class DeterministicFixtureBackend:
    """Deterministic test fixture. It is always labeled as non-weight evidence."""

    name = "deterministic-test-fixture"
    real_weights = False

    def __init__(self, spec: TierSpec) -> None:
        self.spec = spec

    def generate(self, prompt: str, *, max_tokens: int) -> BackendResult:
        output = f"{self.spec.name} governed fixture response: {prompt[:max_tokens]}"
        return BackendResult(
            output=output,
            backend=self.name,
            real_weights=False,
            elapsed_ms=0,
            metadata={"fixture": True},
        )

    def close(self) -> None:
        return None
