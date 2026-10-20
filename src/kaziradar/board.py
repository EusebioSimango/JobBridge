"""Run the searches, apply the filters, and build the ``JobBoard``."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from kaziradar import parsing
from kaziradar.models import LEVEL_NAMES, REMOTE_LABEL, Job, JobBoard, Level
from kaziradar.queries import JobQuery, place_label
from kaziradar.search import Answer, BudgetedSearch, ResponseCache, SearchClient, run_plans

_TYPE_SCHEDULES = {
    "full-time": "Full-time",
    "part-time": "Part-time",
    "contract": "Contract",
    "internship": "Internship",
}


def board_title(query: JobQuery) -> str:
    places = [*map(place_label, query.places), *(["remote"] if query.remote else [])]
    where = places[0] if len(places) == 1 else f"{', '.join(places[:-1])} and {places[-1]}"
    level = f"{LEVEL_NAMES[query.level]} " if query.level in LEVEL_NAMES else ""
    role = query.role if level else query.role[:1].upper() + query.role[1:]
    preposition = "" if where == "remote" else "in "
    return f"{level}{role} jobs {preposition}{where}"


def collect(
    query: JobQuery,
    client: SearchClient,
    *,
    max_searches: int,
    cache: ResponseCache | None,
    today: date | None = None,
) -> tuple[JobBoard, int]:
    """Search, filter and return the board, with the number of searches spent."""
    search = BudgetedSearch(client, max_searches=max_searches, cache=cache)
    place_plans = [plan for plan in query.plans() if plan.place != REMOTE_LABEL]
    answers = run_plans(place_plans, search)
    if query.remote:
        google_filter = next((f for a in answers if (f := parsing.remote_filter(a.payload))), None)
        answers += run_plans([query.remote_plan(google_filter)], search)
    board = build_board(query, answers, today=today)
    return board, search.searches_made


def build_board(query: JobQuery, answers: list[Answer], *, today: date | None = None) -> JobBoard:
    hidden: Counter[str] = Counter()
    seen: set[tuple[str, str]] = set()
    jobs: dict[str, list[Job]] = {}
    for answer in answers:
        kept = []
        for job in parsing.jobs(answer.payload, answer.plan.place):
            reason = hide_reason(job, query)
            # Recruiters repost the same job under their own names, so the company is left out.
            key = (_normalised(job.title), _normalised(job.location))
            if reason is None and key in seen:
                reason = "listed under an earlier place"
            if reason:
                hidden[reason] += 1
                continue
            seen.add(key)
            kept.append(job)
        jobs[answer.plan.place] = sort_jobs(kept, query.level)

    return JobBoard(
        title=board_title(query),
        role=query.role,
        places=[answer.plan.place for answer in answers],
        board_date=today or date.today(),
        level=query.level,
        filters=describe_filters(query),
        jobs=jobs,
        hidden=dict(hidden.most_common()),
        searches=[answer.record for answer in answers],
    )


def hide_reason(job: Job, query: JobQuery) -> str | None:
    """Why the filters hide this job, or ``None`` to keep it."""
    if query.level is not Level.ANY and job.level not in (None, query.level):
        return "at another level"
    if (
        query.job_type
        and job.schedule != _TYPE_SCHEDULES[query.job_type]
        and not (query.job_type == "internship" and _is_intern(job))
    ):
        return "of another job type"
    if query.posted_within is not None and (
        job.posted_days_ago is None or job.posted_days_ago > query.posted_within
    ):
        return f"older than {query.posted_within} days, or undated"
    if query.with_salary and not job.salary:
        return "without a salary"
    if query.no_degree and not job.no_degree_mentioned:
        return "that may ask for a degree"
    if job.place == REMOTE_LABEL and not _is_remote(job):
        return "not remote"
    return None


def sort_jobs(jobs: list[Job], level: Level) -> list[Job]:
    """Jobs that state the level asked for first, then the newest first."""

    def rank(job: Job) -> tuple[int, int]:
        unstated = level is not Level.ANY and job.level is None
        return (unstated, job.posted_days_ago if job.posted_days_ago is not None else 10_000)

    return sorted(jobs, key=rank)


def describe_filters(query: JobQuery) -> list[str]:
    filters = []
    if query.level in LEVEL_NAMES:
        filters.append(LEVEL_NAMES[query.level])
    if query.job_type:
        filters.append(_TYPE_SCHEDULES[query.job_type])
    if query.posted_within:
        filters.append(
            "Posted in the last day" if query.posted_within == 1
            else f"Posted in the last {query.posted_within} days"
        )  # fmt: skip
    if query.with_salary:
        filters.append("Shows a salary")
    if query.no_degree:
        filters.append("No degree mentioned")
    return filters


def _normalised(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#]+", text.lower()))


def _is_remote(job: Job) -> bool:
    location = job.location.lower()
    return job.work_from_home or any(word in location for word in ("anywhere", "remote"))


def _is_intern(job: Job) -> bool:
    return any(word in job.title.lower() for word in ("intern", "learnership", "apprentice"))
