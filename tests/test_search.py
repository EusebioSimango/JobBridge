import pytest

from conftest import JOHANNESBURG, FakeClient, FakeHTTPError
from kaziradar.queries import JobQuery
from kaziradar.search import (
    BudgetedSearch,
    BudgetExceeded,
    ResponseCache,
    SearchFailed,
    run_plans,
    safe_error_message,
)

PARAMS = {"engine": "google_jobs", "q": "nurse", "hl": "en", "location": JOHANNESBURG}


def test_the_sdk_gets_a_copy_of_the_params(client):
    params = dict(PARAMS)
    BudgetedSearch(client, max_searches=1).search(params)

    assert "api_key" not in params


def test_budget_is_enforced(client):
    search = BudgetedSearch(client, max_searches=1)
    search.search(PARAMS)

    with pytest.raises(BudgetExceeded, match="budget of 1"):
        search.search({**PARAMS, "q": "chef"})
    assert search.searches_made == 1


def test_cached_answers_are_free_and_have_no_metadata(client, tmp_path):
    cache = ResponseCache(tmp_path)
    client.responses[JOHANNESBURG] = {"search_metadata": {"id": "1"}, "jobs_results": []}
    BudgetedSearch(client, max_searches=1, cache=cache).search(PARAMS)

    again = BudgetedSearch(client, max_searches=1, cache=cache)
    payload, from_cache = again.search(PARAMS)

    assert from_cache
    assert payload == {"jobs_results": []}
    assert again.searches_made == 0
    assert len(client.requests) == 1
    assert "secret-key" not in "".join(p.read_text() for p in tmp_path.iterdir())


def test_cache_expires(client, tmp_path):
    now = [0.0]
    cache = ResponseCache(tmp_path, ttl_seconds=10, clock=lambda: now[0])
    cache.put(PARAMS, {"jobs_results": []})
    now[0] = 10

    assert cache.get(PARAMS) is None


def test_errors_are_not_cached(client, tmp_path):
    cache = ResponseCache(tmp_path)
    client.responses[JOHANNESBURG] = {"error": "Invalid API key."}
    BudgetedSearch(client, max_searches=1, cache=cache).search(PARAMS)

    assert cache.get(PARAMS) is None


def test_error_messages_never_contain_the_key():
    message = safe_error_message(FakeHTTPError())

    assert message == "SerpApi error 401: Invalid API key."
    assert safe_error_message(TimeoutError("api_key=secret-key")) == (
        "SerpApi request failed (TimeoutError)."
    )


def test_failed_searches_become_records(client):
    client.responses[JOHANNESBURG] = FakeHTTPError()
    search = BudgetedSearch(client, max_searches=1)

    with pytest.raises(SearchFailed):
        search.search(PARAMS)

    answers = run_plans(
        JobQuery("nurse", (JOHANNESBURG,)).plans(), BudgetedSearch(client, max_searches=1)
    )
    assert answers[0].record.error == "SerpApi error 401: Invalid API key."
    assert "secret-key" not in answers[0].record.error


def test_run_plans_keeps_the_order():
    client = FakeClient()
    query = JobQuery("data analyst", ("Lisbon, Portugal", "London, United Kingdom", JOHANNESBURG))

    answers = run_plans(query.plans(), BudgetedSearch(client, max_searches=3))

    assert [a.plan.place for a in answers] == ["Lisbon", "London", "Johannesburg"]
    assert [a.record.result_count for a in answers] == [0, 10, 4]
    assert answers[0].record.error is None
