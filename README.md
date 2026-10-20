# KaziRadar

[![Live Demo](https://img.shields.io/badge/Live_Demo-kaziradar.onrender.com-2ea44f?style=flat-square&logo=fastapi)](https://kaziradar.onrender.com)
[![Tests](https://img.shields.io/github/actions/workflow/status/EusebioSimango/kaziradar/tests.yml?branch=main&style=flat-square&label=tests)](https://github.com/EusebioSimango/kaziradar/actions/workflows/tests.yml)
[![Hackathon](https://img.shields.io/badge/SerpApi-PyCon_ZA_2026-blue?style=flat-square)](https://serpapi.com/pyconzahackathon)
[![SerpApi Python package](https://img.shields.io/badge/SerpApi-Python_package-8A2BE2?style=flat-square)](https://github.com/serpapi/serpapi-python)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=flat-square)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

Find jobs in any field, in the cities and countries you name, abroad or remote, at your experience level. Every job links to where you can apply.

```bash
kaziradar "software developer" --in "Johannesburg, South Africa" --remote --level entry
```

*Kazi* means work in Swahili.

Built for the [SerpApi PyCon ZA 2026 Hackathon](https://serpapi.com/pyconzahackathon).

## Why this exists

At PyCon, and above all at Beginners' Day, one question comes up again and again: *"How do I get a job? Where do I even look?"* People finishing a course, a bootcamp or a degree know what they can do, but not where the openings are, which ones are really for beginners, or which ones they can do from home.

The question is not only about Python, and not only about beginners. A nurse looking at London, an accountant moving to Toronto and a senior engineer who wants remote work all start from the same blank search box. KaziRadar is the bridge from "I am looking" to a short list of real openings with apply links:

- **Any role**: software developer, data analyst, nurse, teacher, chef.
- **Any place**: a city or a country, in Africa or anywhere Google Jobs covers, plus remote jobs.
- **Any level**: `--level entry` for internships, learnerships, graduate programmes and junior roles; `mid` and `senior` for people further along. Each job says *why* it got its level.
- **Filters that matter when you are looking**: job type, posted in the last N days, shows a salary, no degree mentioned.

## What you get

The command above, run with Cape Town as a second place, gives this (the full list is in [`examples/sample-entry-level.md`](examples/sample-entry-level.md)):

```markdown
## Johannesburg

1. **[Junior Software Engineer](https://www.pnet.co.za/jobs--Junior-Software-Engineer-...)** — Placement Specialist Pty Ltd · Johannesburg South, South Africa
   Full-time · 12 days ago
   Entry level: "Junior" in the title
   Apply: [Pnet](https://www.pnet.co.za/jobs--Junior-Software-Engineer-...)

## Remote

1. **[Entry-Level Software Developer](https://...)** — RemoteHive · Anywhere
   Full-time · 6 days ago · Work from home
   Entry level: "Entry-Level" in the title
   Apply: [RemoteHive](https://...) · [Remote Drift](https://...)
```

A second example, [`examples/sample-abroad.md`](examples/sample-abroad.md), lists data analyst jobs in London and Toronto at every level, posted in the last 30 days.

Each job shows its title (linked to the first apply page), company and location; the job type, when it was posted, the salary when the posting has one, "Work from home" and "No degree mentioned"; its level and the reason; and up to 3 apply links, the employer's own careers page first. The footer lists every search sent and how many jobs each filter hid.

### How the filters work

| Filter | What it does |
| --- | --- |
| `--level entry\|mid\|senior` | Adds "entry level" or "senior" to the search, then reads each job's level from its title ("Junior", "Graduate", "Learnership", "Senior", "Lead"), from beginner phrases in the description ("recent graduate", "no experience required"), or from the years of experience it asks for ("0-2 years" is entry level, "2-7 years" is not). Jobs at another level are hidden. Jobs that do not state a level are kept, below the ones that do, and marked "Level not stated in the posting", because many beginner-friendly jobs never say so. |
| `--type full-time\|part-time\|contract\|internship` | Keeps that job type. Internships also match titles with "Intern", "Learnership" or "Apprentice". |
| `--posted 1\|3\|7\|30` | Keeps jobs posted in the last N days. |
| `--with-salary` | Keeps jobs that show a salary. |
| `--no-degree` | Keeps jobs Google marks "No degree mentioned". |
| `--remote` | Adds a remote section, searched with Google's own "Remote" filter (see below). |

The same job is often posted by several recruiters; it is shown once. Text is cleaned up (HTML entities, broken accents, "Company :" prefixes) and tracking parameters are removed from links.

Google Jobs does not cover every country: for example, it has no listings for Maputo or Lisbon. KaziRadar says so for that place, and suggests a nearby city or `--remote`, instead of showing jobs from somewhere else.

## How it uses SerpApi

KaziRadar uses the **[SerpApi Python package](https://github.com/serpapi/serpapi-python)** (`serpapi.Client`) and the **[Google Jobs API](https://serpapi.com/google-jobs-api)** (`engine: google_jobs`).

| Search | Parameters | Per run |
| --- | --- | --- |
| The role, at each place | `q` (role, plus level and type words), `location`, `hl` | one per place |
| Remote jobs | `q` and `uds` from Google's "Remote" filter in the first place's answer, `location` of that place (so the jobs suit your time zone) | one, with `--remote` |

How it fits together, in [`search.py`](src/kaziradar/search.py) and [`board.py`](src/kaziradar/board.py):

- The place searches run in parallel. Google Jobs answers each one with filter chips, and one of them is "Remote", with its own `uds` token. KaziRadar then runs the remote search with that token, so Google itself returns only remote jobs. If no answer offers the chip, it searches "role remote" instead.
- Each job is read from `jobs_results`: `title`, `company_name`, `location`, `extensions` (posted, type, salary, work from home, no degree), `detected_extensions`, `description` and `apply_options`.
- The SDK adds `api_key` to the dict it is given, so it always gets a copy. Errors are reduced to SerpApi's own message: `serpapi.HTTPError` holds the request URL, with the key, and is never printed.
- An empty answer ("Google hasn't returned any results") is a normal result for that place, not a failure.

Searches cost credits, so KaziRadar is careful with them:

- **Cost up front:** the command prints how many searches it may spend (one per place, plus one for remote) before it starts, and how many it made at the end.
- **Budget:** at most 6 searches per run by default (`--max-searches`, up to 20). A run that needs more is refused before any search is sent.
- **Cache:** answers are saved in `~/.cache/kaziradar` for 12 hours, without search metadata, so changing only the filters costs nothing. Use `--no-cache` to search again.

## Run it

You need Python 3.10 or newer, [uv](https://docs.astral.sh/uv/getting-started/installation/) and a free [SerpApi API key](https://serpapi.com/users/sign_up) (250 searches a month).

```bash
git clone https://github.com/EusebioSimango/kaziradar.git
cd kaziradar
uv sync
cp .env.example .env   # then paste your key after SERPAPI_API_KEY=
```

Try it:

```bash
# First jobs in two cities, plus remote ones (3 searches)
uv run kaziradar "software developer" --in "Johannesburg, South Africa" --in "Cape Town, South Africa" --remote --level entry

# Jobs abroad, any level, posted in the last week, that show a salary
uv run kaziradar "nurse" --in "London, United Kingdom" --in "Toronto, Canada" --posted 7 --with-salary

# Internships, saved as Markdown
uv run kaziradar "accountant" --in Nairobi --type internship -o jobs.md

# Remote only, senior roles, as JSON for other tools
uv run kaziradar "data engineer" --remote --level senior --json
```

`--in` takes a city or a country and can be repeated (up to 5). Run `uv run kaziradar --help` for every option. The command exits with code `1` if every search failed and `2` if the API key is missing or an argument is invalid.

## Web demo

The same search as a web page: a role, up to 3 places, "also remote jobs", level, type, date and the two checkboxes. A [sample list](https://kaziradar.onrender.com/example) needs no searches.

Run it locally:

```bash
uv sync --extra web
uv run uvicorn kaziradar.web:app --reload   # http://127.0.0.1:8000
```

The demo runs on a shared SerpApi key, so it protects that key's free plan:

- **Cache:** answers are kept for 12 hours per search, so a visitor who changes only the filters, or repeats a search someone else made, spends nothing.
- **Limits:** at most 40 searches a day for the whole demo (`DEMO_DAILY_SEARCHES`) and 5 new lists per visitor per hour. Visitors are counted by a salted hash of their IP, kept only in memory.
- **No logs:** the server runs with `--no-access-log`, so searches and IP addresses are not written anywhere. Job text is rendered with raw HTML turned off.

To deploy your own copy on [Render](https://render.com), choose **New > Blueprint**, pick this repository ([`render.yaml`](render.yaml) describes the service) and set `SERPAPI_API_KEY`.

## Project layout

| Module | Responsibility |
| --- | --- |
| [`cli.py`](src/kaziradar/cli.py) | The `kaziradar` command, API key loading, writing the output. |
| [`web.py`](src/kaziradar/web.py) | The FastAPI web demo. |
| [`limits.py`](src/kaziradar/limits.py) | The web demo's cache and rate limits. |
| [`queries.py`](src/kaziradar/queries.py) | `JobQuery`: validation and the parameters of each search. |
| [`search.py`](src/kaziradar/search.py) | The `serpapi.Client` wrapper: budget, 12-hour cache, parallel searches, safe errors. |
| [`parsing.py`](src/kaziradar/parsing.py) | Turns Google Jobs JSON into `Job` items: dates, salary, flags, apply links. Pure functions. |
| [`levels.py`](src/kaziradar/levels.py) | Reads a job's experience level, and the reason, from its title and description. |
| [`board.py`](src/kaziradar/board.py) | Runs the searches, including the remote one, and applies the filters. |
| [`render.py`](src/kaziradar/render.py) | Writes the `JobBoard` as Markdown. |
| [`models.py`](src/kaziradar/models.py) | The plain data classes shared by the modules above. |

## Tests

The tests replace `serpapi.Client` with a fake client that returns real Google Jobs answers saved from SerpApi (Johannesburg, London, a remote search and Lisbon's empty answer), so they spend no credits and need no key:

```bash
uv run pytest
```

There is one test file per module. They cover the search parameters and validation, the level rules, reading jobs (extensions, dates, apply links, broken text, tracking parameters), the budget and the cache, errors that never show the key, the remote search with Google's filter, every filter and the duplicate check, the Markdown output, the CLI end to end, and the web demo's limits, cache and HTML escaping. GitHub Actions runs them, with Ruff, on Python 3.10 and 3.13.

## What was added for the hackathon

Everything. KaziRadar is a new project, started on 20 October 2026 for the SerpApi PyCon ZA Hackathon.

## Credits

Built on these open source libraries, used as dependencies under their own licences. No code was copied from them.

- [`serpapi`](https://github.com/serpapi/serpapi-python), the SerpApi Python package (MIT)
- [Typer](https://github.com/fastapi/typer) (MIT), [Rich](https://github.com/Textualize/rich) (MIT) and [python-dotenv](https://github.com/theskumar/python-dotenv) (BSD-3-Clause)
- For the web demo: [FastAPI](https://github.com/fastapi/fastapi) (MIT), [Uvicorn](https://github.com/encode/uvicorn) (BSD-3-Clause) and [markdown-it-py](https://github.com/executablebooks/markdown-it-py) (MIT)
- [pytest](https://github.com/pytest-dev/pytest) (MIT), [HTTPX](https://github.com/encode/httpx) (BSD-3-Clause) and [Ruff](https://github.com/astral-sh/ruff) (MIT), for the tests

## License

[MIT](LICENSE)
