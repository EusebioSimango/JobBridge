"""Command line entry point: ``kaziradar "data analyst" --in Johannesburg --remote``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markdown import Markdown

from kaziradar.board import collect
from kaziradar.models import JobBoard, Level
from kaziradar.queries import JOB_TYPES, POSTED_WITHIN, JobQuery
from kaziradar.render import render_markdown
from kaziradar.search import ResponseCache, default_cache_dir, official_client

DEFAULT_MAX_SEARCHES = 6
EXIT_ALL_SEARCHES_FAILED = 1
EXIT_MISSING_API_KEY = 2
_POSTED_CHOICES = ", ".join(map(str, POSTED_WITHIN))

app = typer.Typer(add_completion=False)
console = Console()
status_console = Console(stderr=True)


@app.command()
def main(
    role: Annotated[str, typer.Argument(help='The job, e.g. "data analyst" or "nurse".')],
    places: Annotated[
        list[str] | None,
        typer.Option(
            "--in",
            "-i",
            help='A city or country to search, e.g. "Cape Town" or Portugal. Repeat for more.',
        ),
    ] = None,
    remote: Annotated[bool, typer.Option("--remote", help="Also search remote jobs.")] = False,
    level: Annotated[
        Level, typer.Option(help="Experience level: any, entry, mid or senior.")
    ] = Level.ANY,
    job_type: Annotated[
        str | None, typer.Option("--type", help=f"One of: {', '.join(JOB_TYPES)}.")
    ] = None,
    posted: Annotated[
        int | None,
        typer.Option(help=f"Only jobs posted in the last N days: {_POSTED_CHOICES}."),
    ] = None,
    with_salary: Annotated[
        bool, typer.Option("--with-salary", help="Only jobs that show a salary.")
    ] = False,
    no_degree: Annotated[
        bool, typer.Option("--no-degree", help="Only jobs where Google sees no degree mentioned.")
    ] = False,
    max_searches: Annotated[
        int, typer.Option(min=1, max=20, help="Most SerpApi searches to spend in this run.")
    ] = DEFAULT_MAX_SEARCHES,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Ignore answers saved in the last 12 hours.")
    ] = False,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Save the list to this file.")
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Output JSON instead of Markdown.")
    ] = False,
) -> None:
    """Find jobs for ROLE in the places you name, abroad or remote, at any experience level."""
    try:
        query = JobQuery(
            role,
            tuple(places or ()),
            remote=remote,
            level=level,
            job_type=job_type,
            posted_within=posted,
            with_salary=with_salary,
            no_degree=no_degree,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None

    planned = len(query.plans())
    if planned > max_searches:
        raise typer.BadParameter(
            f"This needs {planned} searches but --max-searches is {max_searches}. "
            "Use fewer places or raise --max-searches."
        )
    api_key = load_api_key()
    status_console.print(
        f"[dim]Up to {planned} SerpApi {'search' if planned == 1 else 'searches'}: one per place"
        f"{' plus one for remote jobs' if query.remote else ''}. "
        "Answers from the last 12 hours are reused for free.[/dim]"
    )
    cache = None if no_cache else ResponseCache(default_cache_dir())
    try:
        with status_console.status("Searching Google Jobs through SerpApi..."):
            board, searches_made = collect(
                query, official_client(api_key), max_searches=max_searches, cache=cache
            )
    except Exception as exc:
        if os.getenv("KAZIRADAR_DEBUG"):
            raise
        status_console.print(
            f"[red]Error:[/red] unexpected {type(exc).__name__}. "
            "Run with KAZIRADAR_DEBUG=1 for details."
        )
        raise typer.Exit(code=EXIT_ALL_SEARCHES_FAILED) from None

    write_output(board, output=output, as_json=as_json)
    status_console.print(f"[dim]SerpApi searches made: {searches_made}[/dim]")
    if board.all_searches_failed:
        raise typer.Exit(code=EXIT_ALL_SEARCHES_FAILED)


def load_api_key() -> str:
    load_dotenv(find_dotenv(usecwd=True))
    api_key = os.getenv("SERPAPI_API_KEY") or os.getenv("SERPAPI_KEY")
    if not api_key:
        status_console.print(
            "[red]Missing SERPAPI_API_KEY.[/red] Copy .env.example to .env and add your key "
            "from https://serpapi.com/manage-api-key"
        )
        raise typer.Exit(code=EXIT_MISSING_API_KEY)
    return api_key


def write_output(board: JobBoard, *, output: Path | None, as_json: bool) -> None:
    text = (
        json.dumps(board.to_dict(), indent=2, ensure_ascii=False, default=str) + "\n"
        if as_json
        else render_markdown(board)
    )
    if output:
        output.write_text(text, encoding="utf-8")
        status_console.print(f"Saved jobs to [bold]{output}[/bold]")
    elif as_json or not console.is_terminal:
        print(text, end="")
    else:
        console.print(Markdown(text))


if __name__ == "__main__":
    app()
