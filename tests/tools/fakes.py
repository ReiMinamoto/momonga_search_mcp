from __future__ import annotations

from momonga_search_mcp.api import BinaryApiResponse, JsonApiResponse, MomongaApiError


class FakeApiClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []
        self.response: dict[str, object] = {"results": []}
        self.response_headers: dict[str, str] = {}
        self.inferred_compute_credits: int | None = None
        self.binary_response = BinaryApiResponse(
            content=b"file-bytes",
            media_type="application/octet-stream",
            filename=None,
        )
        self.error: MomongaApiError | None = None

    def get(self, path: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append(("GET", path, params))
        if self.error is not None:
            raise self.error
        return self.response

    def get_with_usage(self, path: str, params: dict[str, object] | None = None) -> JsonApiResponse:
        self.calls.append(("GET", path, params))
        if self.error is not None:
            raise self.error
        return JsonApiResponse(
            payload=self.response,
            headers=self.response_headers,
            inferred_compute_credits=self.inferred_compute_credits,
        )

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("POST", path, payload))
        if self.error is not None:
            raise self.error
        return self.response

    def get_binary(self, path: str, params: dict[str, object] | None = None) -> BinaryApiResponse:
        self.calls.append(("GET_BINARY", path, params))
        if self.error is not None:
            raise self.error
        return self.binary_response
