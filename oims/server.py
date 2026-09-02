"""Loopback-only OIMS service for the Collective Quest gateway."""

from __future__ import annotations

import argparse
import json
import threading
from collections.abc import Callable, Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .collective import run_collective_request
from .manifest import FamilyManifest, load_manifest
from .runtime import DEFAULT_ARTIFACTS_DIR, DEFAULT_WEIGHTS_DIR
from .weights import inspect_tier

MAX_REQUEST_BYTES = 256_000
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
RunRequest = Callable[[dict[str, Any]], dict[str, Any]]


def normalize_request(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Request must be a JSON object")
    unknown = sorted(set(value) - {"request_id", "agent", "prompt", "message", "max_tokens"})
    if unknown:
        raise ValueError(f"Unsupported request fields: {', '.join(unknown)}")
    prompt = value.get("prompt", value.get("message"))
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt or message must be a non-empty string")
    try:
        max_tokens = int(value.get("max_tokens", 256))
    except (TypeError, ValueError) as exc:
        raise ValueError("max_tokens must be an integer") from exc
    if not 1 <= max_tokens <= 4096:
        raise ValueError("max_tokens must be between 1 and 4096")
    request: dict[str, Any] = {
        "prompt": prompt,
        "max_tokens": max_tokens,
    }
    for key in ("request_id", "agent"):
        if key in value:
            request[key] = value[key]
    return request


def health_report(
    manifest: FamilyManifest,
    weights_dir: Path,
) -> dict[str, Any]:
    tiers = [inspect_tier(spec, weights_dir, compute_hashes=False) for spec in manifest.tiers]
    ready = all(item["lock_matches_manifest"] and item["size_verified"] for item in tiers)
    return {
        "ok": True,
        "service": "oims",
        "family": manifest.family,
        "loopback_only": True,
        "ready_for_inference": ready,
        "evidence_class": "WEIGHT_BACKED_PENDING_RUNTIME_PROBE" if ready else "WEIGHTS_UNAVAILABLE",
        "tiers": [
            {
                "tier": item["tier"],
                "lock_matches_manifest": item["lock_matches_manifest"],
                "size_verified": item["size_verified"],
            }
            for item in tiers
        ],
    }


def build_handler(
    *,
    runner: RunRequest,
    health: Callable[[], dict[str, Any]],
    inference_lock: threading.BoundedSemaphore,
) -> type[BaseHTTPRequestHandler]:
    class OIMSHandler(BaseHTTPRequestHandler):
        server_version = "OIMS"
        sys_version = ""

        def do_GET(self) -> None:
            if self.path.rstrip("/") != "/health":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            self._json(HTTPStatus.OK, health())

        def do_POST(self) -> None:
            if self.path.rstrip("/") != "/v1/chat":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
                return
            if length <= 0 or length > MAX_REQUEST_BYTES:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request_too_large"})
                return
            try:
                body = json.loads(self.rfile.read(length))
                request = normalize_request(body)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_request", "detail": str(exc)[:300]},
                )
                return

            if not inference_lock.acquire(blocking=False):
                self._json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"error": "model_busy", "retry_after_seconds": 2},
                    headers={"Retry-After": "2"},
                )
                return
            try:
                response = runner(request)
            except Exception as exc:  # noqa: BLE001 - HTTP trust boundary normalizes errors.
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": type(exc).__name__, "detail": str(exc)[:300]},
                )
                return
            finally:
                inference_lock.release()

            lawful = bool(response.get("result", {}).get("lawful", False))
            self._json(
                HTTPStatus.OK if lawful else HTTPStatus.SERVICE_UNAVAILABLE,
                response,
            )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _json(
            self,
            status: HTTPStatus,
            value: dict[str, Any],
            *,
            headers: dict[str, str] | None = None,
        ) -> None:
            encoded = json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, item in (headers or {}).items():
                self.send_header(key, item)
            self.end_headers()
            self.wfile.write(encoded)

    return OIMSHandler


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8310,
    weights_dir: Path = DEFAULT_WEIGHTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> None:
    if host not in LOOPBACK_HOSTS:
        raise ValueError("OIMS service must bind to loopback")
    manifest = load_manifest()
    lock = threading.BoundedSemaphore(1)
    handler = build_handler(
        runner=lambda request: run_collective_request(
            request,
            manifest=manifest,
            weights_dir=weights_dir,
            artifacts_dir=artifacts_dir,
        ),
        health=lambda: health_report(manifest, weights_dir),
        inference_lock=lock,
    )
    with ThreadingHTTPServer((host, port), handler) as server:
        server.daemon_threads = True
        server.serve_forever(poll_interval=0.25)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loopback-only OIMS HTTP service")
    parser.add_argument("--host", default="127.0.0.1", choices=sorted(LOOPBACK_HOSTS))
    parser.add_argument("--port", type=int, default=8310)
    parser.add_argument("--weights-dir", type=Path, default=DEFAULT_WEIGHTS_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    args = parser.parse_args(argv)
    serve(
        host=args.host,
        port=args.port,
        weights_dir=args.weights_dir.expanduser().resolve(),
        artifacts_dir=args.artifacts_dir.expanduser().resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
