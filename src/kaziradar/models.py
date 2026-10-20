"""Plain data shared by the search, filter and render modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any

REMOTE_LABEL = "Remote"


class Level(str, Enum):
    ANY = "any"
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"


LEVEL_NAMES = {Level.ENTRY: "Entry level", Level.MID: "Mid level", Level.SENIOR: "Senior"}


@dataclass(frozen=True)
class ApplyLink:
    title: str
    link: str


@dataclass(frozen=True)
class Job:
    title: str
    company: str
    place: str
    """The search this job came from: a place the user named, or ``REMOTE_LABEL``."""
    location: str = ""
    via: str = ""
    link: str = ""
    """Google's page for the job, with every apply option."""
    posted: str = ""
    """Google's own text, e.g. "3 days ago"."""
    posted_days_ago: int | None = None
    schedule: str = ""
    """e.g. "Full-time", "Internship"."""
    salary: str = ""
    work_from_home: bool = False
    no_degree_mentioned: bool = False
    description: str = ""
    apply_links: tuple[ApplyLink, ...] = ()
    level: Level | None = None
    """The experience level the text points to; ``None`` when it says nothing."""
    level_signals: tuple[str, ...] = ()
    """Why, e.g. ('"Junior" in the title',)."""


@dataclass(frozen=True)
class SearchRecord:
    place: str
    query: str
    location: str
    result_count: int = 0
    error: str | None = None
    from_cache: bool = False


@dataclass
class JobBoard:
    title: str
    role: str
    places: list[str]
    board_date: date
    level: Level = Level.ANY
    filters: list[str] = field(default_factory=list)
    """The filters applied, in words, e.g. ["Entry level", "Posted in the last 7 days"]."""
    jobs: dict[str, list[Job]] = field(default_factory=dict)
    """Jobs by place, in the order the places were given."""
    hidden: dict[str, int] = field(default_factory=dict)
    """How many jobs each filter hid, e.g. {"at another level": 3}."""
    searches: list[SearchRecord] = field(default_factory=list)

    @property
    def job_count(self) -> int:
        return sum(len(jobs) for jobs in self.jobs.values())

    @property
    def all_searches_failed(self) -> bool:
        return bool(self.searches) and all(record.error for record in self.searches)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
