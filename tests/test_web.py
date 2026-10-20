from datetime import date

import pytest
from fastapi.testclient import TestClient

from conftest import JOHANNESBURG
from jobbridge import web
from jobbridge.limits import BoardCache, DemoLimits, LimitReached

SEARCH = {"role": "software developer", "place": JOHANNESBURG, "level": "entry"}


def demo(client, tmp_path, *, daily_searches=100):
    app = web.create_app(lambda: client, daily_searches=daily_searches, cache_dir=tmp_path)
    return TestClient(app)


def test_home_shows_the_form(client, tmp_path):
    page = demo(client, tmp_path).get("/")

    assert page.status_code == 200
    assert '<form action="/jobs"' in page.text
    assert '<option value="senior">Senior</option>' in page.text
    assert client.requests == []


def test_job_list(client, tmp_path):
    page = demo(client, tmp_path).get("/jobs", params={**SEARCH, "remote": "on"})

    assert page.status_code == 200
    assert "<h1>Entry level software developer jobs in Johannesburg and remote</h1>" in page.text
    assert "Junior Software Engineer" in page.text
    assert '<option value="entry" selected>' in page.text
    assert len(client.requests) == 2
    assert "uds" in client.requests[1]


def test_repeat_list_comes_from_the_cache(client, tmp_path):
    browser = demo(client, tmp_path)
    browser.get("/jobs", params=SEARCH)
    browser.get("/jobs", params=SEARCH)

    assert len(client.requests) == 1


def test_searches_already_cached_are_not_charged(client, tmp_path):
    browser = demo(client, tmp_path, daily_searches=1)
    browser.get("/jobs", params=SEARCH)

    page = browser.get("/jobs", params={**SEARCH, "salary": "on"})

    assert page.status_code == 200
    assert len(client.requests) == 1


def test_daily_search_limit_returns_429(client, tmp_path):
    page = demo(client, tmp_path, daily_searches=1).get("/jobs", params={**SEARCH, "remote": "on"})

    assert page.status_code == 429
    assert "Please try again tomorrow" in page.text
    assert client.requests == []


def test_visitor_limit_returns_429(client, tmp_path):
    browser = demo(client, tmp_path)
    headers = {"X-Forwarded-For": "203.0.113.7"}
    for role in ["nurse", "chef", "teacher", "plumber", "driver"]:
        browser.get("/jobs", params={**SEARCH, "role": role}, headers=headers)

    page = browser.get("/jobs", params={**SEARCH, "role": "pilot"}, headers=headers)
    other = browser.get(
        "/jobs", params={**SEARCH, "role": "pilot"}, headers={"X-Forwarded-For": "198.51.100.2"}
    )

    assert page.status_code == 429
    assert "in the last hour" in page.text
    assert other.status_code == 200


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"role": "nurse"}, "at least one place"),
        ({"role": "nurse", "place": ["a", "b", "c", "d"]}, "At most 3 places"),
        ({"role": "nurse", "place": "x" * 61}, "at most 60 characters"),
        ({"role": "nurse", "place": "Accra", "level": "guru"}, "pick a level"),
        ({"role": "nurse", "place": "Accra", "type": "gig"}, "--type"),
    ],
)
def test_invalid_searches_return_400(client, tmp_path, params, message):
    page = demo(client, tmp_path).get("/jobs", params=params)

    assert page.status_code == 400
    assert message in page.text
    assert client.requests == []


def test_input_and_results_are_escaped(client, tmp_path):
    client.responses[JOHANNESBURG]["jobs_results"][0]["title"] = "<script>alert(1)</script> Dev"
    page = demo(client, tmp_path).get(
        "/jobs", params={**SEARCH, "role": '"><img src=x onerror=alert(1)>'}
    )

    assert "<script>alert(1)</script>" not in page.text
    assert "<img src=x" not in page.text


def test_missing_api_key_returns_503(monkeypatch, tmp_path):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    browser = TestClient(web.create_app(cache_dir=tmp_path))

    assert browser.get("/jobs", params=SEARCH).status_code == 503


def test_sample_list_needs_no_searches(client, tmp_path):
    page = demo(client, tmp_path).get("/example")

    assert page.status_code == 200
    assert "Entry level software developer jobs" in page.text
    assert client.requests == []


def test_healthz(client, tmp_path):
    assert demo(client, tmp_path).get("/healthz").text == "ok"


def test_cache_entries_expire():
    now = [0.0]
    cache = BoardCache(ttl_seconds=10, clock=lambda: now[0])
    cache.put("key", "list")
    now[0] = 9
    assert cache.get("key") == "list"
    now[0] = 10
    assert cache.get("key") is None


def test_limits_reset_each_hour_and_each_day():
    now, today = [0.0], [date(2026, 10, 20)]
    limits = DemoLimits(
        daily_searches=4,
        lists_per_visitor_per_hour=1,
        clock=lambda: now[0],
        today=lambda: today[0],
    )
    limits.reserve("ip", 2)
    with pytest.raises(LimitReached):
        limits.reserve("ip", 1)

    now[0] = 3600
    limits.reserve("ip", 2)
    with pytest.raises(LimitReached):
        limits.reserve("other-ip", 1)

    today[0] = date(2026, 10, 21)
    limits.reserve("other-ip", 4)
