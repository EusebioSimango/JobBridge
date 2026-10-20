import json

import pytest
from typer.testing import CliRunner

from conftest import JOHANNESBURG, FakeClient
from jobbridge import cli

runner = CliRunner()


@pytest.fixture
def fake(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setenv("SERPAPI_API_KEY", "secret-key")
    monkeypatch.setattr(cli, "official_client", lambda api_key: client)
    monkeypatch.setattr(cli, "default_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.chdir(tmp_path)
    return client


def test_markdown_list(fake):
    result = runner.invoke(
        cli.app, ["software developer", "--in", JOHANNESBURG, "--level", "entry"]
    )

    assert result.exit_code == 0, result.output
    assert "Entry level software developer jobs in Johannesburg" in result.stdout
    assert "Up to 1 SerpApi search" in result.stderr
    assert "SerpApi searches made: 1" in result.stderr
    assert "secret-key" not in result.output


def test_json_output_to_a_file(fake, tmp_path):
    out = tmp_path / "jobs.json"
    result = runner.invoke(
        cli.app, ["software developer", "-i", JOHANNESBURG, "--remote", "--json", "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["places"] == ["Johannesburg", "Remote"]
    assert "uds" in fake.requests[1]


def test_second_run_uses_the_cache(fake):
    args = ["software developer", "--in", JOHANNESBURG]
    runner.invoke(cli.app, args)
    result = runner.invoke(cli.app, args)

    assert "SerpApi searches made: 0" in result.stderr
    assert len(fake.requests) == 1


def test_too_many_searches_are_refused_before_searching(fake):
    places = [arg for city in ("Accra", "Lagos", "Nairobi") for arg in ("--in", city)]
    result = runner.invoke(cli.app, ["nurse", *places, "--remote", "--max-searches", "3"])

    assert result.exit_code == 2
    assert "needs 4 searches" in result.output
    assert fake.requests == []


def test_invalid_query_is_a_usage_error(fake):
    result = runner.invoke(cli.app, ["nurse"])

    assert result.exit_code == 2
    assert "at least one place" in result.output


def test_missing_key(monkeypatch, tmp_path):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.app, ["nurse", "--in", "Accra"])

    assert result.exit_code == cli.EXIT_MISSING_API_KEY
    assert "Missing SERPAPI_API_KEY" in result.output


def test_all_searches_failing_exits_with_1(fake):
    fake.responses[JOHANNESBURG] = {"error": "Invalid API key."}

    result = runner.invoke(cli.app, ["nurse", "--in", JOHANNESBURG])

    assert result.exit_code == cli.EXIT_ALL_SEARCHES_FAILED
