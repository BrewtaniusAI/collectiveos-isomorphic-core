"""Authenticated loopback service for CollectiveOS role-bound inference."""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .agents import AgentRegistry, load_agent_registry
from .collective import (
    CollectiveRequestError,
    ProfileBackendFactory,
    run_collective_request,
)
from .doctor import run_diagnostics
from .manifest import FamilyManifest, load_manifest
from .runtime import DEFAULT_ARTIFACTS_DIR, DEFAULT_WEIGHTS_DIR


class CollectiveServiceRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    agent: str | None = Field(default=None, min_length=1, max_length=64)
    prompt: str = Field(min_length=1, max_length=12_000)
    max_tokens: int = Field(default=256, ge=1, le=4096)


class OIMSServiceRuntime:
    """Serializes local weight execution and preserves sealed OIMS responses."""

    def __init__(
        self,
        *,
        manifest: FamilyManifest,
        registry: AgentRegistry,
        weights_dir: Path,
        artifacts_dir: Path,
        backend_factory: ProfileBackendFactory | None,
    ) -> None:
        self.manifest = manifest
        self.registry = registry
        self.weights_dir = weights_dir
        self.artifacts_dir = artifacts_dir
        self.backend_factory = backend_factory
        self._inference_lock = asyncio.Lock()

    async def execute(self, payload: CollectiveServiceRequest) -> dict[str, Any]:
        request = payload.model_dump(exclude_none=True)
        async with self._inference_lock:
            return await asyncio.to_thread(
                run_collective_request,
                request,
                manifest=self.manifest,
                registry=self.registry,
                backend_factory=self.backend_factory,
                weights_dir=self.weights_dir,
                artifacts_dir=self.artifacts_dir,
            )


def create_app(
    *,
    service_token: str,
    weights_dir: Path = DEFAULT_WEIGHTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
    backend_factory: ProfileBackendFactory | None = None,
) -> FastAPI:
    if len(service_token.encode("utf-8")) < 32:
        raise ValueError("OIMS service token must contain at least 32 bytes")

    manifest = load_manifest()
    registry = load_agent_registry(manifest=manifest)
    runtime = OIMSServiceRuntime(
        manifest=manifest,
        registry=registry,
        weights_dir=weights_dir,
        artifacts_dir=artifacts_dir,
        backend_factory=backend_factory,
    )
    app = FastAPI(
        title="CollectiveOS Isomorphic Core Service",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def require_service_token(
        authorization: str | None = Header(default=None),
    ) -> None:
        prefix = "Bearer "
        supplied = ""
        if authorization and authorization.startswith(prefix):
            supplied = authorization.removeprefix(prefix).strip()
        if not supplied or not secrets.compare_digest(supplied, service_token):
            raise HTTPException(
                status_code=401,
                detail="OIMS service authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        diagnostics = await asyncio.to_thread(
            run_diagnostics,
            manifest,
            weights_dir,
        )
        return {
            "service": "collectiveos-isomorphic-core",
            "family": manifest.family,
            "status": "ready" if diagnostics["ready_for_family_run"] else "degraded",
            "ready_for_weight_execution": diagnostics["ready_for_family_run"],
            "llama_cpp_installed": diagnostics["llama_cpp_installed"],
            "runtime_version_ready": diagnostics["runtime_version_ready"],
            "gpu_offload_supported": diagnostics["gpu_offload_supported"],
            "weights_ready": diagnostics["weights_ready"],
            "tiers": diagnostics["tiers"],
        }

    @app.post("/v1/collective", dependencies=[Depends(require_service_token)])
    async def collective(payload: CollectiveServiceRequest) -> dict[str, Any]:
        try:
            return await runtime.execute(payload)
        except CollectiveRequestError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="OIMS weight execution unavailable",
            ) from exc

    return app


def require_loopback(host: str) -> str:
    normalized = host.strip().lower()
    if normalized not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("OIMS service may only bind to loopback")
    return host


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oims-service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9319)
    parser.add_argument(
        "--weights-dir",
        type=lambda value: Path(value).expanduser().resolve(),
        default=Path(os.environ.get("OIMS_WEIGHTS_DIR", DEFAULT_WEIGHTS_DIR)).resolve(),
    )
    parser.add_argument(
        "--artifacts-dir",
        type=lambda value: Path(value).expanduser().resolve(),
        default=Path(os.environ.get("OIMS_ARTIFACTS_DIR", DEFAULT_ARTIFACTS_DIR)).resolve(),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.port < 1 or args.port > 65535:
        raise SystemExit("port must be between 1 and 65535")
    try:
        host = require_loopback(args.host)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    service_token = os.environ.get("OIMS_SERVICE_TOKEN", "")
    try:
        app = create_app(
            service_token=service_token,
            weights_dir=args.weights_dir,
            artifacts_dir=args.artifacts_dir,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    uvicorn.run(app, host=host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
