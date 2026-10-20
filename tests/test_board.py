from dataclasses import replace

from conftest import JOHANNESBURG, TODAY, load_fixture
from kaziradar import parsing
from kaziradar.board import board_title, collect, describe_filters, hide_reason, sort_jobs
from kaziradar.models import REMOTE_LABEL, Job, Level
from kaziradar.queries import JobQuery


def job(**changes) -> Job:
    base = Job(
        title="Data Analyst",
        company="Acme",
        place="Lagos",
        location="Lagos, Nigeria",
        via="LinkedIn",
        link="https://example.com/1",
        posted="3 days ago",
        posted_days_ago=3,
        schedule="Full-time",
    )
    return replace(base, **changes)


def run(query, client):
    return collect(query, client, max_searches=len(query.plans()), cache=None, today=TODAY)


def test_remote_search_uses_googles_remote_filter(client, entry_query):
    board, searches = run(entry_query, client)

    assert searches == 2
    assert "uds" not in client.requests[0]
    google_filter = parsing.remote_filter(load_fixture("johannesburg"))
    assert client.requests[1]["uds"] == google_filter["uds"]
    assert board.places == ["Johannesburg", REMOTE_LABEL]
    assert len(board.jobs[REMOTE_LABEL]) == 10
    assert board.title == "Entry level software developer jobs in Johannesburg and remote"


def test_remote_search_without_a_google_filter_adds_the_word(client):
    client.responses[JOHANNESBURG] = {"jobs_results": []}
    query = JobQuery("nurse", (JOHANNESBURG,), remote=True)

    run(query, client)

    assert "uds" not in client.requests[1]
    assert client.requests[1]["q"] == "nurse remote"


def test_other_levels_are_hidden_but_unstated_ones_are_kept(client):
    query = JobQuery("data analyst", ("London, United Kingdom",), level=Level.ENTRY)

    board, _ = run(query, client)

    kept = board.jobs["London"]
    assert all(j.level in (None, Level.ENTRY) for j in kept)
    assert board.hidden["at another level"] >= 4
    assert kept == sort_jobs(kept, Level.ENTRY)


def test_the_same_job_from_two_recruiters_is_shown_once(client):
    payload = load_fixture("johannesburg")
    first = payload["jobs_results"][1]
    payload["jobs_results"].append({**first, "company_name": "Another Recruiter"})
    client.responses[JOHANNESBURG] = payload

    board, _ = run(JobQuery("software developer", (JOHANNESBURG,)), client)

    assert len(board.jobs["Johannesburg"]) == 4
    assert board.hidden == {"listed under an earlier place": 1}


def test_filters_hide_jobs_with_a_reason():
    entry = JobQuery("x", ("Lagos",), level=Level.ENTRY)
    assert hide_reason(job(level=Level.SENIOR), entry) == "at another level"
    assert hide_reason(job(level=None), entry) is None

    part_time = JobQuery("x", ("Lagos",), job_type="part-time")
    assert hide_reason(job(), part_time) == "of another job type"
    internship = JobQuery("x", ("Lagos",), job_type="internship")
    assert hide_reason(job(title="Data Intern"), internship) is None

    week = JobQuery("x", ("Lagos",), posted_within=7)
    assert hide_reason(job(posted_days_ago=8), week) == "older than 7 days, or undated"
    assert hide_reason(job(posted_days_ago=None), week) == "older than 7 days, or undated"

    salary = JobQuery("x", ("Lagos",), with_salary=True)
    assert hide_reason(job(), salary) == "without a salary"
    assert hide_reason(job(salary="NGN 400,000 a month"), salary) is None

    no_degree = JobQuery("x", ("Lagos",), no_degree=True)
    assert hide_reason(job(), no_degree) == "that may ask for a degree"


def test_remote_section_keeps_only_remote_jobs():
    query = JobQuery("x", remote=True)

    assert hide_reason(job(place=REMOTE_LABEL), query) == "not remote"
    assert hide_reason(job(place=REMOTE_LABEL, work_from_home=True), query) is None
    assert hide_reason(job(place=REMOTE_LABEL, location="Anywhere"), query) is None


def test_jobs_that_state_the_level_come_first_then_newest():
    jobs = [
        job(title="a", level=None, posted_days_ago=1),
        job(title="b", level=Level.ENTRY, posted_days_ago=9),
        job(title="c", level=Level.ENTRY, posted_days_ago=2),
        job(title="d", level=Level.ENTRY, posted_days_ago=None),
    ]

    assert [j.title for j in sort_jobs(jobs, Level.ENTRY)] == ["c", "b", "d", "a"]
    assert [j.title for j in sort_jobs(jobs, Level.ANY)] == ["a", "c", "b", "d"]


def test_titles_and_filter_names():
    assert board_title(JobQuery("nurse", ("Lisbon, Portugal", "London"))) == (
        "Nurse jobs in Lisbon and London"
    )
    assert board_title(JobQuery("nurse", remote=True)) == "Nurse jobs remote"
    query = JobQuery("x", ("Lagos",), level=Level.MID, posted_within=1, with_salary=True)
    assert describe_filters(query) == ["Mid level", "Posted in the last day", "Shows a salary"]
