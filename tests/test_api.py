from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from momonga_search_mcp.api import MomongaApiClient, MomongaApiError, api_error_response
from momonga_search_mcp.config import Config


class FakeResponse:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.body = BytesIO(body)
        self.headers = headers or {}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body.read()


class ApiClientTests(unittest.TestCase):
    def test_get_sends_bearer_auth_and_query_params(self) -> None:
        captured: dict[str, object] = {}

        def transport(request: Request, timeout: float) -> FakeResponse:
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            captured["timeout"] = timeout
            return FakeResponse(b'{"ok":true}')

        client = MomongaApiClient(
            Config(api_key="ms_test_xxx", base_url="https://example.test/v1", api_timeout_seconds=7), transport
        )

        result = client.get("/issuers/search", {"q": "abc", "empty": None})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["url"], "https://example.test/v1/issuers/search?q=abc")
        self.assertEqual(captured["auth"], "Bearer ms_test_xxx")
        self.assertEqual(captured["timeout"], 7)

    def test_default_transport_passes_timeout_as_keyword(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(request: Request, *, timeout: float) -> FakeResponse:
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return FakeResponse(b'{"ok":true}')

        client = MomongaApiClient(Config(api_key="ms_test_xxx", base_url="https://example.test/v1", api_timeout_seconds=9))

        with patch("momonga_search_mcp.api.urlopen", fake_urlopen):
            result = client.get("/documents")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["url"], "https://example.test/v1/documents")
        self.assertEqual(captured["timeout"], 9)

    def test_post_sends_json_body(self) -> None:
        captured: dict[str, object] = {}

        def transport(request: Request, timeout: float) -> FakeResponse:
            captured["content_type"] = request.get_header("Content-type")
            captured["data"] = request.data
            return FakeResponse(b'{"results":[]}')

        client = MomongaApiClient(Config(api_key="ms_test_xxx"), transport)

        result = client.post("search/documents", {"query": "価格転嫁", "top_k": 3})

        self.assertEqual(result, {"results": []})
        self.assertEqual(captured["content_type"], "application/json")
        self.assertEqual(captured["data"], b'{"query":"\xe4\xbe\xa1\xe6\xa0\xbc\xe8\xbb\xa2\xe5\xab\x81","top_k":3}')

    def test_get_binary_returns_bytes_and_response_headers(self) -> None:
        captured: dict[str, object] = {}

        def transport(request: Request, timeout: float) -> FakeResponse:
            captured["accept"] = request.get_header("Accept")
            captured["url"] = request.full_url
            return FakeResponse(
                b"%PDF",
                {
                    "Content-Type": "application/pdf",
                    "Content-Disposition": 'attachment; filename="report.pdf"',
                    "Content-Length": "4",
                },
            )

        client = MomongaApiClient(Config(api_key="ms_test_xxx", base_url="https://example.test/v1"), transport)

        result = client.get_binary("/documents/doc_1/originals/pdf")

        self.assertEqual(captured["accept"], "*/*")
        self.assertEqual(captured["url"], "https://example.test/v1/documents/doc_1/originals/pdf")
        self.assertEqual(result.content, b"%PDF")
        self.assertEqual(result.media_type, "application/pdf")
        self.assertEqual(result.filename, "report.pdf")

    def test_maps_problem_details_error_and_retry_after_header(self) -> None:
        def transport(request: Request, timeout: float) -> FakeResponse:
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                {"Retry-After": "12"},
                BytesIO(
                    b'{"type":"https://api.momongasearch.com/errors/rate-limit-exceeded",'
                    b'"title":"Rate limit exceeded","status":429,"code":"rate_limit_exceeded",'
                    b'"detail":"Please retry later."}'
                ),
            )

        client = MomongaApiClient(Config(api_key="ms_test_xxx"), transport)

        with self.assertRaises(MomongaApiError) as context:
            client.get("/documents")

        self.assertEqual(context.exception.status, 429)
        self.assertEqual(context.exception.code, "rate_limit_exceeded")
        self.assertEqual(context.exception.retry_after_seconds, 12)
        self.assertEqual(context.exception.detail, "Please retry later.")

    def test_retry_after_seconds_payload_takes_precedence(self) -> None:
        def transport(request: Request, timeout: float) -> FakeResponse:
            raise HTTPError(
                request.full_url,
                409,
                "Conflict",
                {"Retry-After": "99"},
                BytesIO(
                    b'{"title":"Content not available","status":409,"code":"content_not_available",'
                    b'"detail":"Pending release.","retry_after_seconds":3600}'
                ),
            )

        client = MomongaApiClient(Config(api_key="ms_test_xxx"), transport)

        with self.assertRaises(MomongaApiError) as context:
            client.get("/documents/doc_x/content")

        self.assertEqual(context.exception.code, "content_not_available")
        self.assertEqual(context.exception.retry_after_seconds, 3600)

    def test_maps_timeout(self) -> None:
        def transport(request: Request, timeout: float) -> FakeResponse:
            raise TimeoutError("timed out")

        client = MomongaApiClient(Config(api_key="ms_test_xxx"), transport)

        with self.assertRaises(MomongaApiError) as context:
            client.get("/documents")

        self.assertEqual(context.exception.code, "request_timeout")

    def test_api_error_response_includes_model_facing_details(self) -> None:
        error = MomongaApiError(
            status=409,
            code="content_not_available",
            message="Content not available",
            detail="Pending release.",
            retry_after_seconds=3600,
            payload={
                "document_id": "doc_x",
                "content_status": "pending_release",
                "internal_trace": "secret",
            },
        )

        response = api_error_response(error)

        self.assertEqual(response["ok"], False)
        self.assertEqual(
            response["error"],
            {
                "code": "content_not_available",
                "status": 409,
                "message": "Content not available",
                "next_action": ("Wait for retry_after_seconds before retrying this request."),
                "detail": "Pending release.",
                "retry_after_seconds": 3600,
                "content_status": "pending_release",
                "document_id": "doc_x",
            },
        )

    def test_api_error_response_allows_tool_specific_next_action(self) -> None:
        error = MomongaApiError(status=429, code="quota_exceeded", message="Quota exceeded")

        response = api_error_response(error, next_action="Ask the user whether to continue with cached results only.")

        self.assertEqual(response["error"]["next_action"], "Ask the user whether to continue with cached results only.")


if __name__ == "__main__":
    unittest.main()
