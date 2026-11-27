"""Clientes HTTP reutilizables para pruebas integrales con servicios reales."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: Any


class ApiClient:
    def __init__(self) -> None:
        self.frontend_url = os.getenv("E2E_FRONTEND_URL", "http://localhost:18000")
        self.menu_url = os.getenv("E2E_MENU_URL", "http://localhost:18001")
        self.orders_url = os.getenv("E2E_ORDERS_URL", "http://localhost:18002")
        self.loyalty_url = os.getenv("E2E_LOYALTY_URL", "http://localhost:18003")

    def json(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        query: dict[str, Any] | None = None,
        timeout: float = 5,
    ) -> HttpResult:
        if query:
            url = f"{url}?{urlencode(query)}"
        data = json.dumps(payload).encode() if payload is not None else None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read().decode()
                return HttpResult(
                    response.status,
                    {key.lower(): value for key, value in response.headers.items()},
                    json.loads(raw),
                )
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = raw
            return HttpResult(
                exc.code,
                {key.lower(): value for key, value in exc.headers.items()},
                body,
            )

    def text(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        timeout: float = 5,
    ) -> HttpResult:
        request = Request(
            url,
            data=b"" if method != "GET" else None,
            headers={"Accept": "text/plain", **(headers or {})},
            method=method,
        )
        with urlopen(request, timeout=timeout) as response:
            return HttpResult(
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read().decode(),
            )

    def wait_until_healthy(self, timeout_seconds: int = 90) -> None:
        services = {
            "frontend": self.frontend_url,
            "menu": self.menu_url,
            "orders": self.orders_url,
            "loyalty": self.loyalty_url,
        }
        deadline = time.monotonic() + timeout_seconds
        pending = set(services)
        last_errors: dict[str, str] = {}
        while pending and time.monotonic() < deadline:
            for service in tuple(pending):
                try:
                    result = self.json("GET", f"{services[service]}/health", timeout=2)
                except (URLError, TimeoutError, OSError) as exc:
                    last_errors[service] = str(exc)
                    continue
                if result.status == 200 and result.body.get("status") == "healthy":
                    pending.remove(service)
                else:
                    last_errors[service] = f"HTTP {result.status}: {result.body}"
            if pending:
                time.sleep(1)
        if pending:
            pytest.fail(f"Servicios sin salud: {sorted(pending)}; último error: {last_errors}")


class BrowserSession:
    """Navegador HTTP mínimo con cookies y seguimiento de redirecciones."""

    def __init__(self) -> None:
        self._cookies = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookies))
        self.csrf_token: str | None = None

    def cookie_header(self, url: str) -> str:
        request = Request(url)
        self._cookies.add_cookie_header(request)
        return request.get_header("Cookie", "")

    def request(
        self, method: str, url: str, *, headers: dict[str, str] | None = None
    ) -> HttpResult:
        request_headers = dict(headers or {})
        if method not in {"GET", "HEAD", "OPTIONS"}:
            if self.csrf_token is None:
                parsed = urlsplit(url)
                self.request("GET", f"{parsed.scheme}://{parsed.netloc}/")
            data = urlencode({"csrf_token": self.csrf_token or ""}).encode()
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = None
        request = Request(url, data=data, method=method, headers=request_headers)
        try:
            response = self._opener.open(request, timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read().decode()
            token = re.search(r'name="csrf-token" content="([^"]+)"', body)
            if token:
                self.csrf_token = token[1]
            return HttpResult(
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                body,
            )
