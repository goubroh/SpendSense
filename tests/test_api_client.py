import httpx
import pytest

from dashboard.api_client import APIError, request


def test_404_reports_missing_route_and_restart_hint(monkeypatch):
    def missing_route(*args, **kwargs):
        req = httpx.Request("GET", "http://127.0.0.1:8000/months")
        return httpx.Response(404, json={"detail": "Not Found"}, request=req)

    monkeypatch.setattr(httpx, "request", missing_route)

    with pytest.raises(APIError) as error:
        request("GET", "/months")

    assert error.value.status_code == 404
    assert "GET /months" in str(error.value)
    assert "uvicorn app.api:app --reload" in str(error.value)
