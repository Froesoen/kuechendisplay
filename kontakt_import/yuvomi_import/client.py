"""Duenner HTTP-Client fuer die yuvomi-REST-API (Bearer-API-Token)."""
from __future__ import annotations

import time
from typing import Any

import httpx


class YuvomiError(RuntimeError):
    def __init__(self, status: int, message: str, body: Any = None):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.body = body


class YuvomiClient:
    def __init__(self, base_url: str, token: str, verify_tls: bool = True, timeout: float = 30.0):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/v1",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            verify=verify_tls,
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        for attempt in range(4):
            r = self._http.request(method, path, **kw)
            if r.status_code == 429 and attempt < 3:
                time.sleep(float(r.headers.get("Retry-After", 2 * (attempt + 1))))
                continue
            break
        if r.status_code >= 400:
            try:
                body = r.json()
                msg = body.get("error", r.text) if isinstance(body, dict) else r.text
            except ValueError:
                body, msg = None, r.text
            raise YuvomiError(r.status_code, str(msg), body)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    def list_contacts(self) -> list[dict[str, Any]]:
        return self._request("GET", "/contacts")["data"]

    def list_categories(self) -> list[dict[str, Any]]:
        return self._request("GET", "/contacts/categories")["data"]

    def create_category(self, name: str) -> dict[str, Any]:
        return self._request("POST", "/contacts/categories", json={"name": name})["data"]

    def create_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/contacts", json=payload)["data"]

    def update_contact(self, contact_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", f"/contacts/{contact_id}", json=payload)["data"]
