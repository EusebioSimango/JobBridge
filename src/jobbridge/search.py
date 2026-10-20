"""Google Jobs searches through the official SerpApi Python package, with a budget and a cache."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jobbridge.models import SearchRecord
from jobbridge.queries import SearchPlan

CACHE_SECONDS = 12 * 60 * 60

# SerpApi reports an empty result page through the "error" field with this wording.
NO_RESULTS_MARKER = "hasn't returned any results"


class SearchClient(Protocol):
    def search(self, params: dict[str, Any]) -> Mapping[str, Any]: ...


class SearchFailed(RuntimeError):
    """A search could not run; the message is safe to show and never contains the API key."""


class BudgetExceeded(SearchFailed):
    pass


def official_client(api_key: str, timeout: float = 60.0) -> SearchClient:
    import serpapi

    return serpapi.Client(api_key=api_key, timeout=timeout)


def default_cache_dir() -> Path:
    base = os.getenv("XDG_CACHE_HOME") or "~/.cache"
    return Path(base).expanduser() / "jobbridge"


class ResponseCache:
    """SerpApi answers on disk, one JSON file per set of search parameters."""

    def __init__(
        self,
        directory: Path,
        *,
        ttl_seconds: float = CACHE_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._directory = directory
        self._ttl = ttl_seconds
        self._clock = clock

    def get(self, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            entry = json.loads(self._path(params).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if self._clock() - entry.get("saved_at", 0) >= self._ttl:
            return None
        payload = entry.get("payload")
        return payload if isinstance(payload, dict) else None

    def put(self, params: dict[str, Any], payload: dict[str, Any]) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        entry = {"saved_at": self._clock(), "params": params, "payload": payload}
        self._path(params).write_text(json.dumps(entry), encoding="utf-8")

    def _path(self, params: dict[str, Any]) -> Path:
        digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        return self._directory / f"{digest}.json"


class BudgetedSearch:
    """Answers from the cache for free, otherwise spends one search. Safe across threads."""

    def __init__(
        self,
        client: SearchClient,
        *,
        max_searches: int,
        cache: ResponseCache | None = None,
    ) -> None:
        self._client = client
        self._max_searches = max_searches
        self._cache = cache
        self._lock = threading.Lock()
        self.searches_made = 0

    def search(self, params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Return ``(payload, from_cache)``."""
        cached = self._cache.get(params) if self._cache else None
        if cached is not None:
            return cached, True
        with self._lock:
            if self.searches_made >= self._max_searches:
                raise BudgetExceeded(
                    f"Skipped: the budget of {self._max_searches} SerpApi searches per run is "
                    "used up."
                )
            self.searches_made += 1
        try:
            # The SDK adds api_key to the dict it is given, so it gets a copy.
            payload = _as_dict(self._client.search(dict(params)))
        except Exception as exc:
            raise SearchFailed(safe_error_message(exc)) from exc
        error = str(payload.get("error") or "")
        if self._cache and (not error or NO_RESULTS_MARKER in error):
            self._cache.put(params, _without_metadata(payload))
        return payload, False


@dataclass(frozen=True)
class Answer:
    plan: SearchPlan
    payload: dict[str, Any]
    record: SearchRecord


def run_plans(plans: list[SearchPlan], search: BudgetedSearch) -> list[Answer]:
    """Run every search at once; answers come back in the order of ``plans``."""
    if not plans:
        return []
    with ThreadPoolExecutor(max_workers=len(plans)) as pool:
        return list(pool.map(lambda plan: _ask(search, plan), plans))


def _ask(search: BudgetedSearch, plan: SearchPlan) -> Answer:
    query, location = plan.params["q"], plan.params.get("location", "")
    try:
        payload, from_cache = search.search(plan.params)
    except SearchFailed as exc:
        return Answer(plan, {}, SearchRecord(plan.place, query, location, error=str(exc)))
    error = str(payload.get("error") or "")
    record = SearchRecord(
        plan.place,
        query,
        location,
        result_count=len(payload.get("jobs_results") or []),
        error=None if not error or NO_RESULTS_MARKER in error else error,
        from_cache=from_cache,
    )
    return Answer(plan, payload, record)


def safe_error_message(exc: BaseException) -> str:
    # serpapi.HTTPError carries SerpApi's own message. Its str() includes the request URL,
    # which holds the API key, so it must never be shown.
    message = getattr(exc, "error", None)
    status = getattr(exc, "status_code", None)
    if message and status and status > 0:
        return f"SerpApi error {status}: {message}"
    if message:
        return f"SerpApi error: {message}"
    return f"SerpApi request failed ({type(exc).__name__})."


def _as_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "as_dict"):
        result = result.as_dict()
    if not isinstance(result, Mapping):
        raise TypeError("Unexpected response from SerpApi.")
    return dict(result)


def _without_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    # Metadata and pagination links are not used, and stay out of files on disk.
    return {k: v for k, v in payload.items() if k not in {"search_metadata", "serpapi_pagination"}}
