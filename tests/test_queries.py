import pytest

from kaziradar.models import REMOTE_LABEL, Level
from kaziradar.queries import JobQuery, place_label


def test_one_search_per_place_then_remote(entry_query):
    plans = entry_query.plans()

    assert [plan.place for plan in plans] == ["Johannesburg", REMOTE_LABEL]
    assert plans[0].params == {
        "engine": "google_jobs",
        "q": "entry level software developer",
        "hl": "en",
        "location": "Johannesburg, South Africa",
    }
    assert plans[1].params["q"] == "entry level software developer remote"
    assert plans[1].params["location"] == "Johannesburg, South Africa"


def test_remote_only_search_has_no_location():
    plans = JobQuery("nurse", remote=True).plans()

    assert len(plans) == 1
    assert "location" not in plans[0].params


def test_remote_plan_uses_googles_own_filter(entry_query):
    plan = entry_query.remote_plan({"uds": "TOKEN", "q": "entry level software developer remote"})

    assert plan.params["uds"] == "TOKEN"
    assert plan.params["q"] == "entry level software developer remote"


def test_level_and_type_words_go_in_the_query():
    query = JobQuery("accountant", ("Lagos",), level=Level.SENIOR, job_type="contract")
    assert query.search_text == "senior accountant contract"

    assert JobQuery("accountant", ("Lagos",), level=Level.MID).search_text == "accountant"
    assert JobQuery("chef", ("Lagos",), job_type="internship").search_text == "chef internship"


def test_role_and_places_are_tidied():
    query = JobQuery("  data   analyst ", ("Cape Town", " cape  town ", "Cape Town", " "))

    assert query.role == "data analyst"
    assert query.places == ("Cape Town", "cape town")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"role": " "}, "A role is required"),
        ({"role": "x" * 81, "places": ("Lagos",)}, "at most 80"),
        ({"role": "nurse"}, "at least one place"),
        ({"role": "nurse", "places": tuple("abcdef")}, "At most 5 places"),
        ({"role": "nurse", "places": ("Lagos",), "job_type": "gig"}, "--type"),
        ({"role": "nurse", "places": ("Lagos",), "posted_within": 2}, "--posted"),
    ],
)
def test_invalid_queries_are_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        JobQuery(**kwargs)


def test_place_label_keeps_the_city():
    assert place_label("Cape Town, South Africa") == "Cape Town"
    assert place_label("Portugal") == "Portugal"
