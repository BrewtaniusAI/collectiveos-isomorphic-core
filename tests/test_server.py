from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest
from oims.server import LOOPBACK_HOSTS, build_handler, normalize_request, serve


def test_normalize_request_accepts_gateway_chat_shape() -> None:
    assert normalize_request({"message": "hello", "agent": "Giles"}) == {
        "prompt": "hello",
        "agent": "Giles",
        "max_tokens": 256,
    }


def test_normalize_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        normalize_request({"message": "hello", "shell": "whoami"})


def test_server_rejects_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match="loopback"):
        serve(host="0.0.0.0", port=0)


def test_http_chat_and_health() -> None:
    runner_calls: list[dict] = []

    def runner(request: dict) -> dict:
        runner_calls.append(request)
        return {"result": {"lawful": True, "output": "answer"}, "record_sha256": "a" * 64}

    handler = build_handler(
        runner=runner,
        health=lambda: {"ok": True, "service": "oims"},
        inference_lock=threading.BoundedSemaphore(1),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        connection.request("GET", "/health")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["service"] == "oims"

        body = json.dumps({"message": "hello", "agent": "Giles"})
        connection.request(
            "POST",
            "/v1/chat",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["result"]["output"] == "answer"
        assert runner_calls[0]["prompt"] == "hello"
    finally:
        server.shutdown()
        server.server_close()


def test_loopback_host_set_is_closed() -> None:
    assert LOOPBACK_HOSTS == {"127.0.0.1", "::1", "localhost"}
