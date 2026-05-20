from __future__ import annotations

from momonga_search_mcp.api import MomongaApiError


class FakeApiClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []
        self.response: dict[str, object] = {"results": []}
        self.error: MomongaApiError | None = None

    def get(self, path: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append(("GET", path, params))
        if self.error is not None:
            raise self.error
        return self.response

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("POST", path, payload))
        if self.error is not None:
            raise self.error
        return self.response
