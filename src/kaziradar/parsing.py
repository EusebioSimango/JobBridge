"""Turn Google Jobs JSON into ``Job`` objects. Pure functions, no I/O."""

from __future__ import annotations

import contextlib
import html
import re
from collections.abc import Iterator, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from kaziradar.levels import detect_level
from kaziradar.models import ApplyLink, Job

MAX_APPLY_LINKS = 3

SCHEDULES = {
    "full-time": "Full-time",
    "part-time": "Part-time",
    "contractor": "Contract",
    "contract": "Contract",
    "internship": "Internship",
    "temp work": "Temporary",
    "per diem": "Per diem",
    "volunteer": "Volunteer",
}

# Aggregators and job boards; an apply link that is not one of these is usually the employer's.
JOB_BOARDS = (
    "adzuna", "bebee", "careerjet", "careers24", "expertini", "glassdoor", "go job search",
    "indeed", "job mail", "jobleads", "jobrapido", "jobzmall", "jooble", "linkedin", "monster",
    "pnet", "resumekart", "simplyhired", "talent.com", "trabajo.org", "employment echo",
    "ziprecruiter", "jobted", "whatjobs", "jora", "totaljobs", "reed", "stepstone", "net-empregos",
)  # fmt: skip

_POSTED = re.compile(r"^(\d+)\+?\s+(minute|hour|day|week|month)s?\s+ago$", re.IGNORECASE)
_DAYS_PER_UNIT = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30}
_MOJIBAKE_MARKERS = ("â€", "Ã©", "Ã¡", "Ã£", "Ã§", "Ã³")


def jobs(payload: Mapping[str, Any], place: str) -> list[Job]:
    found = []
    for item in _items(payload, "jobs_results"):
        title = _without_label(clean_text(item.get("title")), "job")
        if not title:
            continue
        company = _without_label(clean_text(item.get("company_name")), "company")
        details = _details(item)
        description = clean_text(item.get("description"))
        level, signals = detect_level(title, description)
        links = apply_links(item, company)
        found.append(
            Job(
                title=title,
                company=company,
                place=place,
                location=clean_text(item.get("location")),
                via=clean_text(item.get("via")).removeprefix("via ").strip(),
                link=links[0].link if links else _link(item.get("share_link")),
                posted=details["posted"],
                posted_days_ago=days_ago(details["posted"]),
                schedule=details["schedule"],
                salary=details["salary"],
                work_from_home=details["work_from_home"],
                no_degree_mentioned=details["no_degree"],
                description=description,
                apply_links=links,
                level=level,
                level_signals=signals,
            )
        )
    return found


def days_ago(text: str) -> int | None:
    """ "3 days ago" -> 3, "5 hours ago" -> 0, "2 weeks ago" -> 14, "30+ days ago" -> 30."""
    lowered = text.lower().strip()
    if lowered in {"just posted", "today"}:
        return 0
    if lowered == "yesterday":
        return 1
    match = _POSTED.match(lowered)
    if not match:
        return None
    return int(match.group(1)) * _DAYS_PER_UNIT[match.group(2).lower()]


def remote_filter(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """The parameters of Google's own "Remote" filter in this answer, if it offers one."""
    for item in _items(payload, "filters"):
        parameters = item.get("parameters")
        if clean_text(item.get("name")).lower() == "remote" and isinstance(parameters, Mapping):
            return dict(parameters)
    return None


def apply_links(item: Mapping[str, Any], company: str) -> tuple[ApplyLink, ...]:
    """The employer's own page first, then job boards in Google's order."""
    options = [
        ApplyLink(clean_text(option.get("title")), _without_tracking(_link(option.get("link"))))
        for option in _items(item, "apply_options")
    ]
    options = [option for option in options if option.title and option.link]
    employer = [option for option in options if _is_employer(option, company)]
    others = [option for option in options if option not in employer]
    return tuple([*employer, *others][:MAX_APPLY_LINKS])


def clean_text(value: Any) -> str:
    if not value:
        return ""
    text = " ".join(html.unescape(str(value)).split())
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        # Some job boards send UTF-8 that was decoded as Windows-1252: "â€“" for "–".
        with contextlib.suppress(UnicodeError):
            text = text.encode("cp1252").decode("utf-8")
    return text


def _without_label(text: str, label: str) -> str:
    """ "Company : Absa" -> "Absa", "Job: Developer" -> "Developer"."""
    return re.sub(rf"^{label}\s*:\s*", "", text, flags=re.IGNORECASE)


def _without_tracking(link: str) -> str:
    parts = urlsplit(link)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_")
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _details(item: Mapping[str, Any]) -> dict[str, Any]:
    """Posted date, schedule, salary and flags, from ``detected_extensions`` and ``extensions``.

    Google often leaves ``detected_extensions`` empty and puts everything in the plain
    ``extensions`` list, e.g. ["3 days ago", "ZAR 55,750–ZAR 72,250 a month", "Full-time"].
    """
    detected = item.get("detected_extensions")
    detected = detected if isinstance(detected, Mapping) else {}
    details: dict[str, Any] = {
        "posted": clean_text(detected.get("posted_at")),
        "schedule": SCHEDULES.get(clean_text(detected.get("schedule_type")).lower(), ""),
        "salary": clean_text(detected.get("salary")),
        "work_from_home": bool(detected.get("work_from_home")),
        "no_degree": "no degree" in clean_text(detected.get("qualifications")).lower(),
    }
    raw = item.get("extensions")
    for text in (clean_text(e) for e in raw) if isinstance(raw, list) else ():
        lowered = text.lower()
        if days_ago(text) is not None:
            details["posted"] = details["posted"] or text
        elif lowered in SCHEDULES:
            details["schedule"] = details["schedule"] or SCHEDULES[lowered]
        elif lowered == "work from home":
            details["work_from_home"] = True
        elif "no degree" in lowered:
            details["no_degree"] = True
        elif any(char.isdigit() for char in text):
            details["salary"] = details["salary"] or text
    return details


def _is_employer(option: ApplyLink, company: str) -> bool:
    title = option.title.lower()
    if any(board in title for board in JOB_BOARDS):
        return False
    first_word = company.lower().split()[0] if company.split() else ""
    return "career" in title or (len(first_word) > 2 and first_word in title)


def _items(payload: Mapping[str, Any], key: str) -> Iterator[Mapping[str, Any]]:
    value = payload.get(key)
    if isinstance(value, list):
        yield from (item for item in value if isinstance(item, Mapping))


def _link(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
