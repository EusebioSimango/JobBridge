import pytest

from conftest import load_fixture
from jobbridge import parsing
from jobbridge.models import Level


def test_jobs_from_a_real_answer():
    jobs = parsing.jobs(load_fixture("johannesburg"), "Johannesburg")

    assert len(jobs) == 4
    absa = jobs[0]
    assert absa.title == "Developer Entry Level System Gt"
    assert absa.company == "Absa"
    assert absa.place == "Johannesburg"
    assert absa.posted == "14 days ago"
    assert absa.posted_days_ago == 14
    assert absa.schedule == "Full-time"
    assert absa.level is Level.ENTRY
    assert absa.link == absa.apply_links[0].link
    assert [link.title for link in absa.apply_links] == ["Jooble", "WhatJobs", "Jobrapido.com"]


def test_salary_and_flags_come_from_extensions():
    jobs = {job.company: job for job in parsing.jobs(load_fixture("london"), "London")}

    assert jobs["Commercial Services Group"].salary == "£32,126.17 a year"
    assert jobs["Commercial Services Group"].no_degree_mentioned
    assert jobs["Funding Circle"].work_from_home
    assert jobs["SCS Railways"].schedule == "Part-time"
    assert jobs["SDG Group"].posted == ""
    assert jobs["SDG Group"].posted_days_ago is None


def test_no_results_gives_no_jobs():
    assert parsing.jobs(load_fixture("lisbon"), "Lisbon") == []
    assert parsing.jobs({"jobs_results": "oops"}, "Lisbon") == []


def test_remote_filter_is_read_from_the_answer():
    remote = parsing.remote_filter(load_fixture("johannesburg"))

    assert remote["q"] == "entry level software developer remote"
    assert remote["uds"].startswith("AJ5uw1")
    assert parsing.remote_filter(load_fixture("lisbon")) is None


@pytest.mark.parametrize(
    ("text", "days"),
    [
        ("Just posted", 0),
        ("5 hours ago", 0),
        ("yesterday", 1),
        ("3 days ago", 3),
        ("2 weeks ago", 14),
        ("30+ days ago", 30),
        ("Full-time", None),
    ],
)
def test_days_ago(text, days):
    assert parsing.days_ago(text) == days


def test_employer_link_comes_first_and_tracking_is_removed():
    item = {
        "apply_options": [
            {"title": "LinkedIn", "link": "https://linkedin.com/jobs/1?utm_source=google"},
            {"title": "Indeed", "link": "https://indeed.com/1"},
            {"title": "Nedbank Careers", "link": "https://jobs.nedbank.co.za/1?id=7&utm_medium=x"},
            {"title": "Glassdoor", "link": "https://glassdoor.com/1"},
            {"title": "", "link": "https://example.com"},
        ]
    }

    links = parsing.apply_links(item, "Nedbank")

    assert [link.title for link in links] == ["Nedbank Careers", "LinkedIn", "Indeed"]
    assert links[0].link == "https://jobs.nedbank.co.za/1?id=7"
    assert links[1].link == "https://linkedin.com/jobs/1"


def test_clean_text_fixes_entities_and_mojibake():
    assert parsing.clean_text("Coder &#8211; Remote") == "Coder – Remote"
    assert parsing.clean_text("C++ Developer â€“ Entry") == "C++ Developer – Entry"
    assert parsing.clean_text("  Data \n Analyst ") == "Data Analyst"
    assert parsing.clean_text(None) == ""


def test_jobs_without_a_title_are_skipped():
    payload = {"jobs_results": [{"title": " ", "company_name": "X"}, {"title": "Nurse"}]}

    assert [job.title for job in parsing.jobs(payload, "Lagos")] == ["Nurse"]
