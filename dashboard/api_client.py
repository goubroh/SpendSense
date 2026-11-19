"""HTTP client for the dashboard's local SpendSense API."""
import os

import httpx


class APIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


API_BASE_URL = os.getenv("SPENDSENSE_API_URL", "http://127.0.0.1:8000").rstrip("/")


def request(method: str, path: str, **kwargs):
    try:
        response = httpx.request(method, f"{API_BASE_URL}{path}", timeout=30, **kwargs)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            body = exc.response.json()
            detail = body.get("detail", exc.response.text) if isinstance(body, dict) else body
        except (AttributeError, ValueError):
            detail = exc.response.text
        message = f"API error ({exc.response.status_code}) for {method.upper()} {path}: {detail}"
        if exc.response.status_code == 404:
            message += ". The API route may be missing; restart this project's API with `python -m uvicorn app.api:app --reload`."
        raise APIError(message, exc.response.status_code, detail) from exc
    except httpx.RequestError as exc:
        raise APIError(f"Cannot connect to SpendSense API at {API_BASE_URL}: {exc}") from exc
    return response.json()
