import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.client import FotmobClient
from app.main import create_app
from app.models import MatchOptionsInput, Query
from app.normalizers import normalize


def fixture(match_id, home="Home", away="Away", kickoff="2026-10-06T18:45:00Z"):
    return {"id": match_id, "home": {"name": home, "score": 1}, "away": {"name": away, "score": 2},
            "status": {"utcTime": kickoff, "scoreStr": "1 - 2", "finished": True}}


def mock_app(tmp_path, raw):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=raw)
    client = TestClient(create_app(data_dir=tmp_path, client=FotmobClient(transport=httpx.MockTransport(handler))))
    return client, requests


def test_match_options_reuses_date_query_configuration():
    options = MatchOptionsInput(date="2026-10-07", timezone="America/New_York", mode="live", timeout=7)
    query = options.to_query()
    assert query == Query(kind="date", date="2026-10-07", timezone="America/New_York", mode="live", timeout=7, sections=["fixtures"])
    assert MatchOptionsInput(date="2026-10-07").timeout == 15


def test_live_options_keep_group_ids_same_names_and_timezones(tmp_path):
    raw = {"date": "20261007", "leagues": [
        {"id": 920749, "primaryId": 9808, "name": "Cup", "matches": [fixture(1001)]},
        {"id": 920751, "primaryId": 9808, "name": "Cup", "matches": [fixture(1002, "Other Home", "Other Away")]},
        {"id": 7, "primaryId": 7, "name": "No games", "matches": []},
    ]}
    client, requests = mock_app(tmp_path, raw)
    response = client.post("/api/match-options", json={"date": "2026-10-07", "timezone": "Asia/Tokyo", "mode": "live", "timeout": 15})
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "fotmob" and data["fetchedAt"]
    assert set(data) == {"source", "fetchedAt", "leagues", "warnings"}
    assert [league["id"] for league in data["leagues"]] == ["920749", "920751"]
    assert [league["name"] for league in data["leagues"]] == ["Cup · ID 920749", "Cup · ID 920751"]
    assert [league["matches"][0]["id"] for league in data["leagues"]] == ["1001", "1002"]
    assert data["leagues"][0]["matches"][0] == {"id": "1001", "home": "Home", "away": "Away", "homeScore": 1, "awayScore": 2,
                                                    "status": "FT", "kickoff": "2026-10-07T03:45:00+09:00", "league": "Cup", "leagueId": "920749"}
    assert len(requests) == 1
    assert requests[0].url.path == "/api/data/matches"
    assert requests[0].url.params["date"] == "20261007"
    assert requests[0].url.params["timezone"] == "Asia/Tokyo"


def test_date_modules_add_group_league_id_with_parent_fallback():
    raw = {"leagues": [
        {"id": 202, "primaryId": 7, "name": "First", "matches": [fixture(1001)]},
        {"primaryId": 303, "name": "Second", "matches": [fixture(1002)]},
        {"name": "Third", "matches": [{**fixture(1003), "leagueId": 404}]},
    ]}
    modules, _, _ = normalize(raw, Query(kind="date", date="2026-10-07"))
    assert [match["leagueId"] for match in modules["fixtures"]] == ["202", "303", "404"]


def test_same_name_leagues_use_country_then_id_without_changing_fixture_labels(tmp_path):
    raw = {"leagues": [
        {"id": 101, "name": "Cup", "ccode": "SWE", "matches": [fixture(1001)]},
        {"id": 102, "name": "Cup", "ccode": "NOR", "matches": [fixture(1002)]},
        {"id": 103, "name": "Cup", "ccode": "NOR", "matches": [fixture(1003)]},
        {"id": 104, "name": "Cup", "matches": [fixture(1004)]},
        {"id": 105, "name": "Cup", "ccode": "CHI", "matches": [fixture(1005)]},
        {"id": 106, "name": "Premier League", "ccode": "ENG", "matches": [fixture(1006)]},
    ]}
    client, _ = mock_app(tmp_path, raw)
    data = client.post("/api/match-options", json={"date": "2026-10-07", "mode": "live"}).json()
    assert [league["name"] for league in data["leagues"]] == ["Cup · SWE", "Cup · NOR · ID 102", "Cup · NOR · ID 103", "Cup · ID 104", "Cup · CHI", "Premier League"]
    assert [league["matches"][0]["league"] for league in data["leagues"]] == ["Cup"] * 5 + ["Premier League"]
    assert data["leagues"][0]["matches"][0]["leagueCountry"] == "SWE"
    assert "leagueCountry" not in data["leagues"][3]["matches"][0]
    modules, _, _ = normalize(raw, Query(kind="date", date="2026-10-07"))
    assert modules["fixtures"][0]["league"] == "Cup"
    assert modules["fixtures"][0]["leagueCountry"] == "SWE"


@pytest.mark.parametrize("raw", [{"leagues": []}, {"leagues": [{"id": 47, "name": "Premier League", "matches": []}]}])
def test_empty_day_returns_no_leagues(tmp_path, raw):
    client, requests = mock_app(tmp_path, raw)
    result = client.post("/api/match-options", json={"date": "2026-10-07", "mode": "live"})
    assert result.status_code == 200
    assert result.json()["leagues"] == []
    assert result.json()["source"] == "fotmob"


def test_unselectable_match_ids_are_excluded_without_inventing_ids(tmp_path):
    raw = {"leagues": [{"id": 47, "name": "League", "matches": [fixture(""), fixture("../1"), fixture(1234)]}]}
    client, _ = mock_app(tmp_path, raw)
    result = client.post("/api/match-options", json={"date": "2026-10-07", "mode": "live"}).json()
    assert [match["id"] for match in result["leagues"][0]["matches"]] == ["1234"]
    assert result["warnings"]
    assert "2" in result["warnings"][0]


@pytest.mark.parametrize("payload", [
    {"date": "2026-02-30"}, {"date": "20261007"}, {"date": "2026-10-07", "timezone": "Nowhere/Zone"},
    {"date": "2026-10-07", "timeout": 0}, {"date": "2026-10-07", "timeout": 61},
    {"date": "2026-10-07", "mode": "other"}, {"date": "2026-10-07", "id": "1234"}, {},
])
def test_options_have_strict_date_timezone_timeout_validation(tmp_path, payload):
    client, requests = mock_app(tmp_path, {"leagues": []})
    result = client.post("/api/match-options", json=payload)
    assert result.status_code == 422
    assert result.json()["error"]["code"] == "VALIDATION_ERROR"
    assert requests == []


def test_options_propagate_live_rate_limit_and_retry_after(tmp_path):
    upstream = FotmobClient(transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "45"})))
    client = TestClient(create_app(data_dir=tmp_path, client=upstream))
    result = client.post("/api/match-options", json={"date": "2026-10-07", "mode": "live"})
    assert result.status_code == 429
    assert result.json()["error"]["code"] == "RATE_LIMITED"
    assert result.json()["error"]["retryAfter"] == "45"
    assert "leagues" not in result.json()


def test_demo_options_and_every_detail_are_consistent_across_two_leagues(tmp_path):
    # Demo requests must never touch the live provider.
    def forbidden(request):
        raise AssertionError("demo performed a network request")
    client = TestClient(create_app(data_dir=tmp_path, client=FotmobClient(transport=httpx.MockTransport(forbidden))))
    response = client.post("/api/match-options", json={"date": "2026-10-09", "timezone": "Europe/London", "mode": "demo"})
    assert response.status_code == 200
    result = response.json()
    assert result["source"] == "demo" and result["warnings"]
    assert len(result["leagues"]) >= 2
    ids = set()
    for league in result["leagues"]:
        assert league["matches"]
        for match in league["matches"]:
            assert match["id"] not in ids
            ids.add(match["id"])
            assert match["leagueId"] == league["id"]
            details = client.post("/api/query", json={"kind": "match", "id": match["id"], "date": "2026-10-09", "timezone": "Europe/London", "mode": "demo"}).json()
            scoreboard = details["modules"]["scoreboard"]
            assert scoreboard["home"]["name"] == match["home"]
            assert scoreboard["away"]["name"] == match["away"]
            assert scoreboard["home"]["score"] == match["homeScore"]
            assert scoreboard["away"]["score"] == match["awayScore"]
            assert scoreboard["league"] == match["league"]
            assert scoreboard["status"] == match["status"]
            assert scoreboard["kickoff"] == match["kickoff"]
            assert scoreboard["kickoff"].startswith("2026-10-09T")
            assert scoreboard["kickoff"].endswith("+01:00")
            assert details["modules"]["lineup"]["home"]["name"] == match["home"]
            assert details["modules"]["lineup"]["away"]["name"] == match["away"]
    assert "5315746" in ids
    original = client.post("/api/query", json={"kind": "match", "id": "5315746", "mode": "demo"}).json()["modules"]["scoreboard"]
    assert original["home"]["name"] == "Chelsea" and original["away"]["name"] == "Manchester City"
    assert original["home"]["score"] == 2 and original["away"]["score"] == 1


def test_match_options_do_not_mutate_cached_date_json(tmp_path):
    raw = {"leagues": [{"id": 47, "name": "League", "matches": [fixture(1234)]}]}
    original = copy.deepcopy(raw)
    client, requests = mock_app(tmp_path, raw)
    one = client.post("/api/match-options", json={"date": "2026-10-07", "mode": "live"}).json()
    two = client.post("/api/query", json={"kind": "date", "date": "2026-10-07", "mode": "live", "sections": ["fixtures"]}).json()
    assert one["leagues"][0]["matches"] == two["modules"]["fixtures"]
    assert one["fetchedAt"] == two["fetchedAt"]
    assert len(requests) == 1
    assert raw == original


def test_malformed_country_metadata_returns_custom_error_not_generic_500(tmp_path):
    raw = {"leagues": [{"id": 47, "name": "Cup", "ccode": {"unexpected": "ENG"}, "matches": [fixture(1234)]}]}
    client, _ = mock_app(tmp_path, raw)
    result = client.post("/api/match-options", json={"date": "2026-10-07", "mode": "live"})
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "INVALID_RESPONSE"


def test_grouping_type_failures_use_the_same_custom_response(tmp_path, monkeypatch):
    client, _ = mock_app(tmp_path, {"leagues": [{"id": 47, "name": "Cup", "matches": [fixture(1234)]}]})
    def malformed_group(data):
        raise TypeError("unhashable upstream group metadata")
    monkeypatch.setattr("app.main.match_options", malformed_group)
    result = client.post("/api/match-options", json={"date": "2026-10-07", "mode": "live"})
    assert result.status_code == 502
    assert result.json()["error"]["code"] == "INVALID_RESPONSE"
