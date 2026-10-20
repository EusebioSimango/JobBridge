import pytest

from kaziradar.levels import detect_level
from kaziradar.models import Level


@pytest.mark.parametrize(
    ("title", "level", "signal"),
    [
        ("Junior Software Engineer", Level.ENTRY, '"Junior" in the title'),
        ("Graduate Programme: Finance", Level.ENTRY, '"Graduate" in the title'),
        ("IT Learnership 2027", Level.ENTRY, '"Learnership" in the title'),
        ("C# Developer (Intermediate)", Level.MID, '"Intermediate" in the title'),
        ("Senior Data Analyst", Level.SENIOR, '"Senior" in the title'),
        ("Head of Nursing", Level.SENIOR, '"Head Of" in the title'),
    ],
)
def test_title_words_set_the_level(title, level, signal):
    assert detect_level(title) == (level, (signal,))


def test_senior_words_in_the_title_win():
    assert detect_level("Senior or Junior Developer")[0] is Level.SENIOR


def test_words_inside_other_words_do_not_count():
    assert detect_level("Internal Auditor") == (None, ())
    assert detect_level("Leadership Coach") == (None, ())


def test_description_can_say_entry_level():
    level, signals = detect_level("Software Developer", "Perfect for a recent graduate.")

    assert level is Level.ENTRY
    assert signals == ('"recent graduate" in the description',)


def test_senior_words_in_descriptions_are_ignored():
    assert detect_level("Developer", "You will work with senior engineers.") == (None, ())


@pytest.mark.parametrize(
    ("description", "level"),
    [
        ("At least 1 year of experience.", Level.ENTRY),
        ("0-2 years experience in sales.", Level.ENTRY),
        ("2-7 years experience in analytics.", Level.MID),
        ("3 to 5 years' experience.", Level.MID),
        ("Minimum 8+ years of experience.", Level.SENIOR),
    ],
)
def test_years_of_experience(description, level):
    assert detect_level("Analyst", description)[0] is level
