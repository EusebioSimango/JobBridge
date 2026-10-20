"""Read a job's experience level from its title and description, and say why."""

from __future__ import annotations

import re

from jobbridge.models import Level

# Words that set the level when they are in the title.
TITLE_WORDS = {
    Level.ENTRY: (
        "junior", "jr", "graduate", "grad", "intern", "internship", "trainee", "apprentice",
        "apprenticeship", "learnership", "entry level", "entry-level", "early career",
    ),
    Level.MID: ("mid-level", "mid level", "intermediate"),
    Level.SENIOR: ("senior", "sr", "lead", "principal", "head of", "director", "chief"),
}  # fmt: skip

# Phrases in a description that only appear in jobs meant for people starting out. Senior
# words are not read from descriptions: "you will work with senior engineers" says nothing.
DESCRIPTION_ENTRY_PHRASES = (
    "entry level", "entry-level", "no experience required", "no prior experience",
    "no experience needed", "graduate programme", "graduate program", "recent graduate",
    "learnership", "internship programme", "internship program",
)  # fmt: skip

# "2+ years of experience", "3-5 years' experience", "minimum of 5 years experience".
_YEARS = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*)?years?['’]?\s+(?:of\s+)?(?:\w+\s+){0,3}?"
    r"experience",
    re.IGNORECASE,
)


def detect_level(title: str, description: str = "") -> tuple[Level | None, tuple[str, ...]]:
    """The level and the signals behind it; ``(None, ())`` when the text says nothing."""
    for level in (Level.SENIOR, Level.MID, Level.ENTRY):
        word = _first_word(title, TITLE_WORDS[level])
        if word:
            return level, (f'"{word.title()}" in the title',)

    lowered = description.lower()
    phrase = next((p for p in DESCRIPTION_ENTRY_PHRASES if p in lowered), None)
    if phrase:
        return Level.ENTRY, (f'"{phrase}" in the description',)

    years = _YEARS.search(description)
    if years:
        return _level_for_years(int(years.group(1)), years.group(2)), (
            f'asks for "{" ".join(years.group(0).split())}"',
        )
    return None, ()


def _level_for_years(minimum: int, maximum: str | None) -> Level:
    """ "0-2 years" is entry level, "2-7 years" is not: a wide range is aimed above its floor."""
    if minimum >= 5:
        return Level.SENIOR
    if minimum <= 2 and (maximum is None or int(maximum) <= 3):
        return Level.ENTRY
    return Level.MID


def _first_word(text: str, words: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    for word in words:
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lowered):
            return word
    return None
