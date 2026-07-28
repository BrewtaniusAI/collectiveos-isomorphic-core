from pathlib import Path

from fastapi.testclient import TestClient

from oims.backends import DeterministicFixtureBackend
from oims.service import create_app, require_loopback


TOKEN = "s" * 32


def build_client(tmp_path: Path) -> TestClient:
    app = create_app(
        service_token=TOKEN,
        weights_dir=tmp_path / "weights",
        artifacts_dir=tmp_path / "artifacts",
        backend_factory=lambda spec, _profile: DeterministicFixtureBackend(spec),
    )
    return TestClient(app)


def test_collective_service_requires_exact_bearer_token(tmp_path: Path) -> None:
    client = build_client(tmp_path)
    request = {"request_id": "req-1", "agent": "Giles", "prompt": "Plan safely."}

    assert client.post("/v1/collective", json=request).status_code == 401
    assert (
        client.post(
            "/v1/collective",
            headers={"Authorization": "Bearer wrong"},
            json=request,
        ).status_code
        == 401
    )

    response = client.post(
        "/v1/collective",
        headers={"Authorization": f"Bearer {TOKEN}"},
        json=request,
    )
    assert response.status_code == 200
    result = response.json()
    assert result["@type"] == "CollectiveOIMSResponse"
    assert result["request_id"] == "req-1"
    assert result["agent_binding"]["profile_id"] == "giles-strategist"
    assert result["result"]["lawful"] is True
    assert result["result"]["backend"]["real_weights"] is False


def test_health_reports_degraded_instead_of_simulated_weight_readiness(
    tmp_path: Path,
) -> None:
    response = build_client(tmp_path).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["ready_for_weight_execution"] is False
    assert payload["weights_ready"] is False


def test_service_rejects_non_loopback_binding() -> None:
    assert require_loopback("127.0.0.1") == "127.0.0.1"
    assert require_loopback("localhost") == "localhost"

    try:
        require_loopback("0.0.0.0")
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("remote OIMS binding must be rejected")
