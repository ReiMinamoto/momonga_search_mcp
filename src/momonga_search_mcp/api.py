"""HTTP client for the Momonga Search API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
from typing import Any, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from momonga_search_mcp.config import Config

Transport = Callable[[Request, float], BinaryIO]
PUBLIC_ERROR_FIELDS = (
    "content_status",
    "document_id",
    "reference_url",
    "retry_after_seconds",
)


@dataclass(frozen=True)
class MomongaApiError(RuntimeError):
    status: int | None
    code: str
    message: str
    detail: str | None = None
    retry_after_seconds: int | None = None
    payload: dict[str, Any] | None = None

    def __str__(self) -> str:
        if self.detail:
            return f"{self.code}: {self.detail}"
        return f"{self.code}: {self.message}"


class MomongaApiClient:
    def __init__(self, config: Config, transport: Transport | None = None) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.api_key = config.api_key
        self.timeout_seconds = config.api_timeout_seconds
        self._transport = _default_transport if transport is None else transport

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", path, payload=payload)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._url(path, params)
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "momonga-search-mcp/0.1",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with self._transport(request, self.timeout_seconds) as response:
                return _decode_json(response.read())
        except HTTPError as exc:
            raise _api_error_from_http_error(exc) from exc
        except TimeoutError as exc:
            raise MomongaApiError(None, "request_timeout", "Momonga Search API request timed out") from exc
        except URLError as exc:
            raise MomongaApiError(None, "network_error", "Momonga Search API request failed", detail=str(exc.reason)) from exc

    def _url(self, path: str, params: dict[str, Any] | None) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{normalized_path}"
        if not params:
            return url
        query = urlencode(_clean_params(params), doseq=True)
        return f"{url}?{query}"


def api_error_response(error: MomongaApiError, *, next_action: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": error.code,
        "status": error.status,
        "message": error.message,
        "next_action": next_action or _default_next_action(error),
    }
    if error.detail:
        payload["detail"] = error.detail
    if error.retry_after_seconds is not None:
        payload["retry_after_seconds"] = error.retry_after_seconds

    if error.payload:
        for field in PUBLIC_ERROR_FIELDS:
            if field in payload:
                continue
            value = error.payload.get(field)
            if isinstance(value, str | int | float | bool):
                payload[field] = value

    return {"ok": False, "error": payload}


def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def _default_transport(request: Request, timeout: float) -> BinaryIO:
    return urlopen(request, timeout=timeout)


def _decode_json(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {}
    try:
        decoded = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MomongaApiError(None, "invalid_response", "Momonga Search API returned invalid JSON") from exc
    if not isinstance(decoded, dict):
        raise MomongaApiError(None, "invalid_response", "Momonga Search API returned a non-object JSON response")
    return decoded


def _api_error_from_http_error(exc: HTTPError) -> MomongaApiError:
    payload = _safe_decode_error_payload(exc)
    code = _error_code(exc.code, payload)
    message = _error_message(exc, payload)
    detail = payload.get("detail") if isinstance(payload.get("detail"), str) else None
    retry_after_seconds = _retry_after_seconds(exc.headers.get("Retry-After"), payload)
    return MomongaApiError(
        status=exc.code,
        code=code,
        message=message,
        detail=detail,
        retry_after_seconds=retry_after_seconds,
        payload=payload or None,
    )


def _safe_decode_error_payload(exc: HTTPError) -> dict[str, Any]:
    try:
        return _decode_json(exc.read())
    except MomongaApiError:
        return {}


def _error_code(status: int, payload: dict[str, Any]) -> str:
    code = payload.get("code")
    if isinstance(code, str) and code:
        return code
    if status == 401:
        return "authentication_failed"
    if status == 429:
        return "rate_limited"
    return f"http_{status}"


def _error_message(exc: HTTPError, payload: dict[str, Any]) -> str:
    title = payload.get("title")
    if isinstance(title, str) and title:
        return title
    return exc.reason or f"HTTP {exc.code}"


def _retry_after_seconds(header_value: str | None, payload: dict[str, Any]) -> int | None:
    retry_after = payload.get("retry_after_seconds")
    if isinstance(retry_after, int) and retry_after >= 0:
        return retry_after
    if header_value is None:
        return None
    stripped = header_value.strip()
    if not stripped:
        return None
    if stripped.isdecimal():
        return int(stripped)

    try:
        retry_at = parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0, int((retry_at - datetime.now(UTC)).total_seconds()))


def _default_next_action(error: MomongaApiError) -> str:
    if error.retry_after_seconds is not None or error.code in {"rate_limit_exceeded", "rate_limited"}:
        return "Wait for retry_after_seconds before retrying this request."
    if error.code == "quota_exceeded":
        return "Stop calling credit-consuming tools for this session unless the user changes quota or task scope."
    if error.code in {"invalid_api_key", "authentication_required", "authentication_failed"}:
        return "Check the Momonga Search API key configuration before retrying."
    if error.code in {"request_timeout", "search_backend_timeout"}:
        return "Retry once with a short backoff; if it continues, narrow the query or reduce requested results."
    if error.code == "content_not_available":
        return "Do not retry the same content request immediately; inspect content_status and use available metadata or references."
    if error.code in {"network_error", "invalid_response"}:
        return "Retry once; if the error persists, report the API connectivity or response issue."
    return "Do not repeat the same request unchanged; adjust inputs or report the error details to the user."
