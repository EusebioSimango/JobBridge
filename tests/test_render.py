from conftest import JOHANNESBURG, TODAY, FakeClient, FakeHTTPError
from jobbridge.board import collect
from jobbridge.models import Level
from jobbridge.queries import JobQuery
from jobbridge.render import render_markdown


def markdown(query, client=None):
    client = client or FakeClient()
    board, _ = collect(query, client, max_searches=len(query.plans()), cache=None, today=TODAY)
    return render_markdown(board)


def test_job_list(entry_query):
    text = markdown(entry_query)

    assert text.startswith("# Entry level software developer jobs in Johannesburg and remote\n")
    assert (
        "**Places:** Johannesburg, Remote · **Filters:** Entry level · **Date:** 20 Oct 2026"
        in text
    )
    assert "## Johannesburg\n\n1. **[Junior Software Engineer](" in text
    assert 'Entry level: "Junior" in the title' in text
    assert "Apply: [Pnet](" in text
    assert (
        "| Remote | `entry level software developer remote` | Johannesburg, South Africa | 10 |"
        in text
    )
    assert "never pay to apply" in text


def test_level_not_stated_is_said_when_a_level_was_asked():
    text = markdown(JobQuery("data analyst", ("London, United Kingdom",), level=Level.ENTRY))

    assert "Level not stated in the posting" in text


def test_place_without_listings_says_why():
    text = markdown(JobQuery("data analyst", ("Lisbon, Portugal",)))

    assert "## Lisbon\n\n_Google Jobs has no listings here for this search." in text
    assert "does not cover every country" in text
    assert "> No jobs found, from 1 SerpApi search." in text


def test_place_where_filters_hide_everything():
    text = markdown(
        JobQuery("software developer", (JOHANNESBURG,), with_salary=True, posted_within=1)
    )

    assert "_Google Jobs listed 4, but none match the filters._" in text
    assert "Hidden by the filters:" in text


def test_failed_search_is_reported():
    client = FakeClient({JOHANNESBURG: FakeHTTPError()})

    text = markdown(JobQuery("nurse", (JOHANNESBURG,)), client)

    assert "_Search failed: SerpApi error 401: Invalid API key._" in text
    assert "| Failed: SerpApi error 401: Invalid API key. |" in text
