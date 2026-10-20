"""Render a ``JobBoard`` as Markdown. Formatting only; no decisions about content."""

from __future__ import annotations

from datetime import date

from jobbridge.models import LEVEL_NAMES, REMOTE_LABEL, Job, JobBoard, Level, SearchRecord


def render_markdown(board: JobBoard) -> str:
    blocks = [_header(board), *(_place(board, place) for place in board.places), _footer(board)]
    return "\n\n".join(block for block in blocks if block).rstrip() + "\n"


def format_date(value: date) -> str:
    return f"{value.day} {value:%b %Y}"


def _header(board: JobBoard) -> str:
    facts = [f"**Places:** {', '.join(board.places)}"]
    if board.filters:
        facts.append(f"**Filters:** {', '.join(board.filters)}")
    facts.append(f"**Date:** {format_date(board.board_date)}")
    searches = _plural(len(board.searches), "SerpApi search", "SerpApi searches")
    found = _plural(board.job_count, "job") if board.job_count else "No jobs found"
    return "\n\n".join([f"# {board.title}", " · ".join(facts), f"> {found}, from {searches}."])


def _place(board: JobBoard, place: str) -> str:
    record = _record_for(board, place)
    jobs = board.jobs.get(place, [])
    title = f"## {place}"
    if record and record.error:
        return f"{title}\n\n_Search failed: {record.error}_"
    if jobs:
        items = "\n".join(f"{i}. {_job(job, board.level)}" for i, job in enumerate(jobs, start=1))
        return f"{title}\n\n{items}"
    if record and record.result_count:
        return f"{title}\n\n_Google Jobs listed {record.result_count}, but none match the filters._"
    hint = (
        "Try other words for the role."
        if place == REMOTE_LABEL
        else "Google Jobs does not cover every country; try a nearby city or `--remote`."
    )
    return f"{title}\n\n_Google Jobs has no listings here for this search. {hint}_"


def _job(job: Job, level_asked: Level) -> str:
    title = _link_text(job.title)
    line = f"**[{title}]({job.link})**" if job.link else f"**{title}**"
    where = " · ".join(part for part in (job.company, job.location) if part)
    if where:
        line += f" — {where}"
    lines = [line]
    facts = [job.schedule, job.posted, job.salary]
    facts += ["Work from home" if job.work_from_home else "", _no_degree(job)]
    if any(facts):
        lines.append(" · ".join(fact for fact in facts if fact))
    if job.level:
        lines.append(f"{LEVEL_NAMES[job.level]}: {', '.join(job.level_signals)}")
    elif level_asked is not Level.ANY:
        lines.append("Level not stated in the posting")
    if job.apply_links:
        links = " · ".join(f"[{_link_text(a.title)}]({a.link})" for a in job.apply_links)
        lines.append(f"Apply: {links}")
    # Two trailing spaces make a Markdown line break, so each fact keeps its own line.
    return "  \n   ".join(lines)


def _no_degree(job: Job) -> str:
    return "No degree mentioned" if job.no_degree_mentioned else ""


def _footer(board: JobBoard) -> str:
    rows = [
        "| For | Query | Location | Results |",
        "| --- | --- | --- | --- |",
        *(_search_row(record) for record in board.searches),
    ]
    notes = []
    if board.hidden:
        reasons = ", ".join(f"{count} {reason}" for reason, count in board.hidden.items())
        notes.append(f"Hidden by the filters: {reasons}.")
    notes.append(
        "Results come from Google Jobs, through SerpApi. Check each offer on the employer's "
        "own site, and never pay to apply for a job."
    )
    return "\n\n".join(["---", "### Searches used", "\n".join(rows), f"_{' '.join(notes)}_"])


def _search_row(record: SearchRecord) -> str:
    if record.error:
        outcome = f"Failed: {record.error}"
    elif record.from_cache:
        outcome = f"{record.result_count} (cached)"
    else:
        outcome = str(record.result_count)
    cells = [record.place, f"`{record.query}`", record.location or "-", outcome]
    return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


def _record_for(board: JobBoard, place: str) -> SearchRecord | None:
    return next((record for record in board.searches if record.place == place), None)


def _link_text(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"
