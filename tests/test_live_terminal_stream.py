import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.supervisor.store import SupervisorCommandStore


@pytest.mark.asyncio
async def test_live_terminal_sse_stream_endpoint(tmp_path):
    with TestClient(app) as client:
        supervisor = app.state.supervisor
        original_store = supervisor.store
        supervisor.store = SupervisorCommandStore(
            ttl_seconds=3600,
            max_events=100,
            database_path=tmp_path / "supervisor-test.db",
        )
        try:
            # 1. Create a command
            create_res = client.post(
                "/v1/supervisor/commands",
                json={"goal": "Live stream test goal", "auto_start": False},
                headers={"X-Prometheus-CSRF": "1"},
            )
            assert create_res.status_code == 200
            cmd_id = create_res.json()["id"]

            # 2. Test stream endpoint
            stream_res = client.get(f"/v1/supervisor/commands/{cmd_id}/stream")
            assert stream_res.status_code == 200
            assert "text/event-stream" in stream_res.headers["content-type"]
            assert "Live stream test goal" in stream_res.text
            assert "[END_OF_STREAM]" in stream_res.text
        finally:
            supervisor.store = original_store
