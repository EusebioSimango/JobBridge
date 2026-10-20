"""Decide what to search: one Google Jobs search per place, plus one for remote jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jobbridge.models import REMOTE_LABEL, Level

ENGINE = "google_jobs"
MAX_PLACES = 5
MAX_ROLE_LENGTH = 80
JOB_TYPES = ("full-time", "part-time", "contract", "internship")
POSTED_WITHIN = (1, 3, 7, 30)

# Words Google Jobs understands in the query itself; its own filter chips do the same.
_LEVEL_WORDS = {Level.ENTRY: "entry level", Level.SENIOR: "senior"}
_TYPE_WORDS = {"part-time": "part time", "contract": "contract", "internship": "internship"}


@dataclass(frozen=True)
class SearchPlan:
    place: str
    """The label shown to the user: a place they typed, or ``REMOTE_LABEL``."""
    params: dict[str, Any]


@dataclass(frozen=True)
class JobQuery:
    role: str
    places: tuple[str, ...] = ()
    remote: bool = False
    level: Level = Level.ANY
    job_type: str | None = None
    posted_within: int | None = None
    """Only jobs posted in the last N days."""
    with_salary: bool = False
    no_degree: bool = False
    language: str = "en"

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", " ".join(self.role.split()))
        places = tuple(dict.fromkeys(" ".join(p.split()) for p in self.places if p.strip()))
        object.__setattr__(self, "places", places)
        if not self.role:
            raise ValueError('A role is required, e.g. "data analyst".')
        if len(self.role) > MAX_ROLE_LENGTH:
            raise ValueError(f"The role can be at most {MAX_ROLE_LENGTH} characters.")
        if not self.places and not self.remote:
            raise ValueError("Give at least one place with --in, or use --remote.")
        if len(self.places) > MAX_PLACES:
            raise ValueError(f"At most {MAX_PLACES} places per search.")
        if self.job_type is not None and self.job_type not in JOB_TYPES:
            raise ValueError(f"--type must be one of: {', '.join(JOB_TYPES)}.")
        if self.posted_within is not None and self.posted_within not in POSTED_WITHIN:
            days = ", ".join(str(d) for d in POSTED_WITHIN)
            raise ValueError(f"--posted must be one of: {days} (days).")

    @property
    def search_text(self) -> str:
        words = [self.role]
        if self.level in _LEVEL_WORDS:
            words.insert(0, _LEVEL_WORDS[self.level])
        if self.job_type in _TYPE_WORDS:
            words.append(_TYPE_WORDS[self.job_type])
        return " ".join(words)

    def plans(self) -> list[SearchPlan]:
        """The place searches, then the remote one (see ``remote_plan``)."""
        plans = [
            SearchPlan(place_label(place), self._params(self.search_text, place))
            for place in self.places
        ]
        if self.remote:
            plans.append(self.remote_plan())
        return plans

    def remote_plan(self, google_filter: dict[str, Any] | None = None) -> SearchPlan:
        """Remote jobs, searched from the first place so they suit the user's time zone.

        Google Jobs offers its own "Remote" filter (a ``uds`` token) in the answer to a place
        search; with it, Google itself keeps only remote jobs. Without one, "remote" is added
        to the query, which Google reads the same way, less strictly.
        """
        near = self.places[0] if self.places else None
        params = self._params(f"{self.search_text} remote", near)
        if google_filter and google_filter.get("uds"):
            params["q"] = google_filter.get("q") or params["q"]
            params["uds"] = google_filter["uds"]
        return SearchPlan(REMOTE_LABEL, params)

    def _params(self, text: str, location: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"engine": ENGINE, "q": text, "hl": self.language}
        if location:
            params["location"] = location
        return params


def place_label(place: str) -> str:
    """ "Cape Town, South Africa" -> "Cape Town"; the full name is still what is searched."""
    return place.split(",")[0].strip() or place
