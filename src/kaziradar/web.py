"""Public web demo: a job search form and its results, with limits that protect the budget.

Run locally with ``uv run --extra web uvicorn kaziradar.web:app --reload``.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from html import escape
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, PlainTextResponse
from markdown_it import MarkdownIt

from kaziradar.board import collect
from kaziradar.limits import BoardCache, DemoLimits, LimitReached
from kaziradar.models import REMOTE_LABEL, Level
from kaziradar.queries import JOB_TYPES, MAX_ROLE_LENGTH, POSTED_WITHIN, JobQuery
from kaziradar.render import render_markdown
from kaziradar.search import ResponseCache, SearchClient, official_client

MAX_PLACES = 3
MAX_PLACE_LENGTH = 60
DEFAULT_DAILY_SEARCHES = 40
LISTS_PER_VISITOR_PER_HOUR = 5

REPO_URL = "https://github.com/EusebioSimango/kaziradar"
SAMPLE_LIST = Path(__file__).resolve().parents[2] / "examples" / "sample-entry-level.md"

# Raw HTML in search results is shown as text, never rendered.
_markdown = MarkdownIt("commonmark", {"html": False}).enable("table")


class DemoNotConfigured(RuntimeError):
    """The server has no SerpApi key."""


def create_app(
    client_factory: Callable[[], SearchClient] | None = None,
    *,
    daily_searches: int | None = None,
    cache_dir: Path | None = None,
) -> FastAPI:
    limits = DemoLimits(
        daily_searches=daily_searches or _daily_searches_from_env(),
        lists_per_visitor_per_hour=LISTS_PER_VISITOR_PER_HOUR,
    )
    boards = BoardCache()
    answers = ResponseCache(cache_dir or Path(tempfile.gettempdir()) / "kaziradar-demo")
    make_client = client_factory or _client_from_env
    app = FastAPI(title="KaziRadar", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _page("KaziRadar", _intro() + _form({}))

    @app.get("/jobs", response_class=HTMLResponse)
    async def jobs(request: Request) -> HTMLResponse:
        fields = dict(request.query_params)
        places = request.query_params.getlist("place")
        form = _form(fields, places)
        try:
            query = _query_from(fields, places)
        except ValueError as exc:
            return _message_page(400, str(exc), form)

        key = repr(query)
        markdown = boards.get(key)
        if markdown is None:
            # The remote search's parameters depend on the place answers, so it always counts.
            new_searches = sum(
                plan.place == REMOTE_LABEL or answers.get(plan.params) is None
                for plan in query.plans()
            )
            try:
                client = make_client()
                if new_searches:
                    limits.reserve(_visitor_ip(request), new_searches)
            except DemoNotConfigured:
                return _message_page(503, "The demo is not configured yet.", form)
            except LimitReached as exc:
                return _message_page(429, str(exc), form)
            board, _ = await run_in_threadpool(
                collect, query, client, max_searches=len(query.plans()), cache=answers
            )
            markdown = render_markdown(board)
            if not board.all_searches_failed:
                boards.put(key, markdown)
        return HTMLResponse(_page(query.role, form + _list_html(markdown)))

    @app.get("/example", response_class=HTMLResponse)
    def example() -> HTMLResponse:
        if not SAMPLE_LIST.is_file():
            return _message_page(404, "The sample list is not available.", _form({}))
        markdown = SAMPLE_LIST.read_text(encoding="utf-8")
        return HTMLResponse(_page("Sample job list", _form({}) + _list_html(markdown)))

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok"

    return app


def _query_from(fields: dict[str, str], places: list[str]) -> JobQuery:
    places = [p.strip() for p in places if p.strip()]
    if len(places) > MAX_PLACES:
        raise ValueError(f"At most {MAX_PLACES} places.")
    if any(len(place) > MAX_PLACE_LENGTH for place in places):
        raise ValueError(f"Each place can be at most {MAX_PLACE_LENGTH} characters.")
    try:
        level = Level(fields.get("level") or "any")
    except ValueError:
        raise ValueError("Please pick a level from the list.") from None
    posted = fields.get("posted") or ""
    return JobQuery(
        fields.get("role", ""),
        tuple(places),
        remote=fields.get("remote") == "on",
        level=level,
        job_type=fields.get("type") or None,
        posted_within=int(posted) if posted.isdigit() else None,
        with_salary=fields.get("salary") == "on",
        no_degree=fields.get("no_degree") == "on",
    )


def _client_from_env() -> SearchClient:
    api_key = os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")
    if not api_key:
        raise DemoNotConfigured
    return official_client(api_key)


def _daily_searches_from_env() -> int:
    value = os.getenv("DEMO_DAILY_SEARCHES", "")
    return int(value) if value.isdigit() and int(value) > 0 else DEFAULT_DAILY_SEARCHES


def _visitor_ip(request: Request) -> str:
    # Render puts the client IP first in X-Forwarded-For. A visitor can spoof it, which is
    # why the daily cap, not this per-visitor cap, is what bounds the credits spent.
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _list_html(markdown: str) -> str:
    return f'<article class="jobs">{_markdown.render(markdown)}</article>'


def _message_page(status_code: int, message: str, form: str) -> HTMLResponse:
    notice = f'<p class="notice">{escape(message)}</p>'
    return HTMLResponse(_page("KaziRadar", form + notice), status_code=status_code)


def _intro() -> str:
    return (
        "<p>Find jobs in any field, in the places you name, abroad or remote, at the level "
        "you are at: from internships and graduate programmes to senior roles. Every job "
        "links to where you can apply. Each place costs one SerpApi search, and answers "
        "are reused for 12 hours.</p>"
        '<p><a href="/example">See a sample list</a> (no searches needed).</p>'
    )


def _form(fields: dict[str, str], places: list[str] | None = None) -> str:
    def value(name: str) -> str:
        return escape(fields.get(name, ""))

    def checked(name: str) -> str:
        return " checked" if fields.get(name) == "on" else ""

    def options(name: str, choices: list[tuple[str, str]]) -> str:
        current = fields.get(name, "")
        return "".join(
            f'<option value="{escape(v)}"{" selected" if v == current else ""}>{escape(label)}'
            "</option>"
            for v, label in choices
        )

    levels = [("any", "Any level"), ("entry", "Entry level"), ("mid", "Mid level")]
    levels.append(("senior", "Senior"))
    types = [("", "Any type"), *((t, t.capitalize()) for t in JOB_TYPES)]
    posted = [
        ("", "Any time"),
        *((str(d), f"Last {d} days" if d > 1 else "Last day") for d in POSTED_WITHIN),
    ]
    typed = [*(places or [])[:MAX_PLACES], *[""] * MAX_PLACES][:MAX_PLACES]
    examples = ["Johannesburg, South Africa", "London, United Kingdom", "Toronto, Canada"]
    place_inputs = "\n".join(
        f'    <input name="place" value="{escape(place)}" maxlength="{MAX_PLACE_LENGTH}" '
        f'aria-label="Place {i}" placeholder="{examples[i - 1]}">'
        for i, place in enumerate(typed, start=1)
    )
    return f"""
<form action="/jobs" method="get">
  <label>Role
    <input name="role" value="{value("role")}" maxlength="{MAX_ROLE_LENGTH}" required
      placeholder="software developer, nurse, accountant...">
  </label>
  <fieldset>
    <legend>Places <small>(a city or a country, up to {MAX_PLACES})</small></legend>
{place_inputs}
  </fieldset>
  <label class="inline"><input type="checkbox" name="remote"{checked("remote")}>
    Also remote jobs</label>
  <div class="row">
    <label>Level <select name="level">{options("level", levels)}</select></label>
    <label>Type <select name="type">{options("type", types)}</select></label>
    <label>Posted <select name="posted">{options("posted", posted)}</select></label>
  </div>
  <label class="inline"><input type="checkbox" name="salary"{checked("salary")}>
    Only jobs that show a salary</label>
  <label class="inline"><input type="checkbox" name="no_degree"{checked("no_degree")}>
    Only jobs with no degree mentioned</label>
  <button type="submit">Find jobs</button>
</form>"""


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · KaziRadar</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 46rem; margin: 2rem auto;
         padding: 0 1rem; line-height: 1.5; color: #1f2328; }}
  header a {{ color: inherit; text-decoration: none; }}
  form {{ display: grid; gap: .75rem; margin: 1.5rem 0; }}
  label {{ display: grid; gap: .25rem; font-weight: 600; }}
  fieldset {{ display: grid; gap: .5rem; border: 0; padding: 0; margin: 0; }}
  legend {{ font-weight: 600; margin-bottom: .25rem; }}
  label.inline {{ display: flex; gap: .5rem; align-items: center; font-weight: 400; }}
  .row {{ display: grid; gap: .75rem;
          grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); }}
  input, select {{ font: inherit; padding: .5rem; border: 1px solid #c9ced6; border-radius: 6px; }}
  input[type=checkbox] {{ padding: 0; }}
  button {{ font: inherit; padding: .6rem; border: 0; border-radius: 6px;
           background: #1f6feb; color: white; cursor: pointer; }}
  .notice {{ padding: .75rem 1rem; border-radius: 6px; background: #fff4e5; }}
  .jobs {{ border-top: 1px solid #d0d7de; margin-top: 1.5rem; }}
  .jobs li {{ margin-bottom: .75rem; }}
  .jobs table {{ border-collapse: collapse; font-size: .9rem; }}
  .jobs th, .jobs td {{ border: 1px solid #d0d7de; padding: .3rem .5rem; }}
  footer {{ margin-top: 3rem; font-size: .85rem; color: #57606a; }}
</style>
</head>
<body>
<header><h1><a href="/">KaziRadar</a></h1></header>
{body}
<footer>
  <p>Results come from Google Jobs, through SerpApi; links go to employers and job boards.
  Never pay to apply for a job. This demo makes at most {LISTS_PER_VISITOR_PER_HOUR} new
  searches per visitor per hour and has a small daily limit. Searches and IP addresses are
  not logged.</p>
  <p><a href="{REPO_URL}">Source code and CLI</a>: run it with your own free SerpApi key.</p>
</footer>
</body>
</html>"""


app = create_app()
