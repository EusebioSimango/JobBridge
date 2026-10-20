from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from kaziradar.models import Level
from kaziradar.queries import JobQuery

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 20)
NO_RESULTS = {"error": "Google hasn't returned any results for this query."}
JOHANNESBURG = "Johannesburg, South Africa"


def load_fixture(name: str) -> dict[str, Any]:
    """Real Google Jobs answers from SerpApi, without search metadata."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class FakeHTTPError(Exception):
    """Shaped like ``serpapi.HTTPError``, whose str() holds the URL with the API key."""

    def __init__(self) -> None:
        super().__init__("401 for url https://serpapi.com/search?api_key=secret-key")
        self.error = "Invalid API key."
        self.status_code = 401


class FakeClient:
    """Stands in for ``serpapi.Client`` so tests spend no credits.

    Answers by location, and by ``remote`` when Google's Remote filter (``uds``) is used.
    A response can be an exception, to simulate a failed search.
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {
            JOHANNESBURG: load_fixture("johannesburg"),
            "remote": load_fixture("remote"),
            "London, United Kingdom": load_fixture("london"),
            "Lisbon, Portugal": load_fixture("lisbon"),
        }
        self.requests: list[dict[str, Any]] = []

    def search(self, params: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(dict(params))
        params["api_key"] = "secret-key"  # The real SDK changes the dict it is given.
        key = "remote" if "uds" in params else params.get("location")
        response = self.responses.get(key, NO_RESULTS)
        if isinstance(response, Exception):
            raise response
        return json.loads(json.dumps(response))


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def entry_query() -> JobQuery:
    return JobQuery("software developer", (JOHANNESBURG,), remote=True, level=Level.ENTRY)
