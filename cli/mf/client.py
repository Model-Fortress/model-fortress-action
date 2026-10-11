"""Minimal, dependency-free HTTP client for the Model Fortress API.

Stdlib only (urllib) so it runs in any CI image without `pip install` of extras.
Auth is a Personal Access Token sent as a Bearer token. The base URL points at the
customer's own instance (SaaS at au2mait.com, or a marketplace-provisioned tenant) —
nothing here is cloud-specific.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class ApiError(Exception):
    """Transport / HTTP / usage error (maps to exit code 2)."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class GateTimeout(Exception):
    """Timed out waiting for a job to finish (maps to exit code 1 — build fails)."""


class Client:
    def __init__(self, api_base: str, token: str, tenant: str, timeout: int = 30) -> None:
        if not api_base:
            raise ApiError("API base URL is required (--api-base or MF_API_BASE)")
        if not token:
            raise ApiError("a Personal Access Token is required (--token or MF_TOKEN)")
        if not tenant:
            raise ApiError("a tenant id is required (--tenant or MF_TENANT)")
        self.base = api_base.rstrip("/")
        self.token = token
        self.tenant = tenant
        self.timeout = timeout

    def _url(self, path: str, query: str = "") -> str:
        url = f"{self.base}/tenant/{self.tenant}{path}"
        return f"{url}?{query}" if query else url

    def request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        query: str = "",
        raw: bool = False,
    ) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "*/*"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self._url(path, query), data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:400]
            raise ApiError(f"HTTP {e.code} on {method} {path}: {detail}", code=e.code)
        except urllib.error.URLError as e:
            raise ApiError(f"could not reach {self.base}: {e.reason}")
        if raw:
            return payload
        if not payload:
            return {}
        try:
            return json.loads(payload.decode())
        except ValueError:
            raise ApiError("unexpected non-JSON response from the API")

    def get(self, path: str, query: str = "") -> Any:
        return self.request("GET", path, query=query)

    def post(self, path: str, body: dict | None = None) -> Any:
        return self.request("POST", path, body=body)

    @staticmethod
    def data(resp: Any) -> Any:
        """Unwrap the API's { "data": ... } envelope when present."""
        if isinstance(resp, dict) and "data" in resp:
            return resp["data"]
        return resp
