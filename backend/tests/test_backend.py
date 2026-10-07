import asyncio
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.client import FotmobClient
from app.errors import AccessDeniedError, InvalidResponseError, NetworkError, NotFoundError, RateLimitError, RequestTimeoutError
from app.export import make_export
from app.main import create_app
from app.models import Query, SceneInput
from app.normalizers import normalize
from app.store import SceneStore

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_actual_reference_match_schema_and_timezone():
    query = Query(kind="match", id="5315746", timezone="Asia/Tokyo")
    modules, warnings, unavailable = normalize(load_fixture("match_reference.json"), query)
    assert modules["scoreboard"]["home"]["name"] == "Chelsea"
    assert modules["scoreboard"]["home"]["score"] == 0
    assert modules["scoreboard"]["away"]["score"] == 1
    assert modules["scoreboard"]["kickoff"] == "2026-05-16T23:00:00+09:00"
    assert modules["stats"][0] == {"label": "Ball possession", "home": "44%", "away": "56%"}
    assert modules["lineup"]["home"]["players"][0]["name"] == "Robert Sánchez"
    assert modules["lineup"]["home"]["players"][0]["position"] == "GK"
    assert "standings" in unavailable


def test_date_leagues_are_flattened_without_fabricated_stats():
    raw = load_fixture("date_reference.json")
    query = Query(kind="date", date="2026-05-16", sections=["fixtures", "stats"])
    modules, warnings, unavailable = normalize(raw, query)
    assert len(modules["fixtures"]) == 3
    assert modules["fixtures"][0]["league"] == raw["leagues"][0]["name"]
    assert modules["fixtures"][0]["homeScore"] == 1
    assert "stats" not in modules
    assert unavailable == ["stats"]
    assert warnings
    empty, _, missing = normalize({"leagues": []}, Query(kind="date", date="2026-01-01"))
    assert empty == {"fixtures": []} and missing == []


def test_current_team_squad_season_stats_and_composite_table():
    modules, _, _ = normalize(load_fixture("team_current.json"), Query(kind="team", id="8455"))
    assert modules["team"]["name"] == "Chelsea"
    assert modules["team"]["venue"] == "Stamford Bridge"
    assert modules["team"]["coach"]
    assert len(modules["squad"]) == 4
    assert modules["stats"][0] == {"label": "FotMob rating", "home": 6.9, "away": None}
    assert modules["standings"][0]["played"] is not None
    assert modules["standings"][0]["goalsFor"] is not None
    assert len(modules["fixtures"]) == 2


def test_current_league_top_stats_are_named_and_never_comparative():
    modules, _, _ = normalize(load_fixture("league_current.json"), Query(kind="league", id="47"))
    assert modules["league"]["name"] == "Premier League"
    assert modules["league"]["season"] == "2026/2027"
    assert "Manchester City" in modules["stats"][0]["label"]
    assert modules["stats"][0]["away"] is None
    assert len(modules["standings"]) == 3


@pytest.mark.parametrize("raw,kind", [
    ({"general": {"homeTeam": {"name": "H"}, "awayTeam": {"name": "A"}}, "header": {"teams": None}, "content": {"lineup": {"homeTeam": {"name": "H", "starters": None}, "awayTeam": {"name": "A", "starters": None}}, "stats": {"Periods": {"All": {"stats": None}}}}}, "match"),
    ({"details": {"name": "T"}, "fixtures": {"allMatches": None}, "squad": {"squad": None}, "stats": {"teams": None}}, "team"),
    ({"leagues": [{"matches": None}]}, "date"),
])
def test_nullable_upstream_containers_do_not_crash(raw, kind):
    query = Query(kind=kind, id="1" if kind != "date" else None, date="2026-01-01" if kind == "date" else None)
    normalize(raw, query)


def test_scorestr_wins_over_shootout_total():
    raw = {"leagues": [{"name": "Cup", "matches": [{"id": 1, "home": {"name": "H", "score": 4}, "away": {"name": "A", "score": 3}, "status": {"scoreStr": "1 - 1", "reason": {"short": "Pen"}}}]}]}
    modules, _, _ = normalize(raw, Query(kind="date", date="2026-01-01"))
    assert modules["fixtures"][0]["homeScore"] == 1


@pytest.mark.parametrize("status,error", [(404, NotFoundError), (429, RateLimitError), (403, AccessDeniedError)])
def test_http_error_classes_and_no_automatic_retry(status, error):
    calls = []
    def handler(request):
        calls.append(request.url)
        return httpx.Response(status, headers={"Retry-After": "60"}, json={})
    client = FotmobClient(transport=httpx.MockTransport(handler))
    with pytest.raises(error) as caught:
        asyncio.run(client.fetch(Query(kind="team", id="8455")))
    assert len(calls) == 1
    if status == 429:
        assert caught.value.retry_after == "60"


def test_invalid_json_and_network_errors():
    client = FotmobClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<html>")))
    with pytest.raises(InvalidResponseError):
        asyncio.run(client.fetch(Query(kind="team", id="1")))
    def fail(request):
        raise httpx.ConnectError("offline", request=request)
    with pytest.raises(NetworkError):
        asyncio.run(FotmobClient(transport=httpx.MockTransport(fail)).fetch(Query(kind="team", id="1")))


def test_build_id_refreshes_once_for_stale_deployment():
    calls = []
    def handler(request):
        path = request.url.path
        calls.append(path)
        if path == "/":
            build = "old" if calls.count("/") == 1 else "new"
            return httpx.Response(200, text=f'{{"buildId":"{build}"}}')
        if path.startswith("/_next/data/old/"):
            return httpx.Response(404)
        if "/match/" in path:
            return httpx.Response(200, json={"pageProps": {"__N_REDIRECT": "/matches/chelsea-vs-city/abc#1"}})
        return httpx.Response(200, json={"pageProps": {"general": {"matchId": "1"}}})
    data, _ = asyncio.run(FotmobClient(transport=httpx.MockTransport(handler)).fetch(Query(kind="match", id="1")))
    assert data["general"]["matchId"] == "1"
    assert calls.count("/") == 2
    assert calls[-1] == "/_next/data/new/matches/chelsea-vs-city/abc.json"


def test_total_match_timeout_spans_build_redirect_and_data():
    async def handler(request):
        await asyncio.sleep(0.4)
        if request.url.path == "/":
            return httpx.Response(200, text='{"buildId":"test"}')
        if "/match/" in request.url.path:
            return httpx.Response(200, json={"pageProps": {"__N_REDIRECT": "/matches/home-vs-away/abc#1"}})
        return httpx.Response(200, json={"pageProps": {"general": {"matchId": "1"}}})
    with pytest.raises(RequestTimeoutError):
        asyncio.run(FotmobClient(transport=httpx.MockTransport(handler)).fetch(Query(kind="match", id="1", timeout=1)))


def test_current_next_match_route_can_return_full_pageprops_directly():
    calls = []
    raw = load_fixture("match_reference.json")
    def handler(request):
        calls.append(request.url.path)
        if request.url.path == "/":
            return httpx.Response(200, text='{"buildId":"current"}')
        return httpx.Response(200, json={"pageProps": raw})
    result, _ = asyncio.run(FotmobClient(transport=httpx.MockTransport(handler)).fetch(Query(kind="match", id="5315746")))
    assert result["general"]["matchId"] == "5315746"
    assert calls == ["/", "/_next/data/current/match/5315746.json"]


def test_short_cache_preserves_real_fetch_time_and_returns_copies():
    calls = []
    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"details": {"name": "Chelsea"}})
    client = FotmobClient(transport=httpx.MockTransport(handler))
    async def fetch_twice():
        query = Query(kind="team", id="8455")
        first, stamp = await client.fetch(query)
        first["details"]["name"] = "modified"
        second, same_stamp = await client.fetch(query)
        return second, stamp, same_stamp
    second, stamp, same_stamp = asyncio.run(fetch_twice())
    assert second["details"]["name"] == "Chelsea"
    assert stamp == same_stamp and len(calls) == 1


def test_sqlite_scenes_persist_and_do_not_upsert_missing(tmp_path):
    first = SceneStore(tmp_path)
    scene = first.create(SceneInput(name="Scene", query=Query(kind="match", id="1", mode="demo")))
    second = SceneStore(tmp_path)
    assert second.get(scene["id"]) == scene
    changed = second.update(scene["id"], SceneInput.model_validate({**scene, "name": "Changed"}))
    assert first.get(scene["id"])["name"] == "Changed"
    with pytest.raises(NotFoundError):
        first.update("missing", SceneInput.model_validate(changed))
    second.delete(scene["id"])
    assert first.list() == []


def test_api_validation_scene_filter_and_export(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get("/api/health").json()["status"] == "ok"
    invalid = client.post("/api/query", json={"kind": "date", "date": "2026-99-01", "mode": "demo"})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    response = client.post("/api/scenes", json={"name": "Broadcast", "query": {"kind": "match", "id": "5315746", "mode": "demo"}, "sections": ["stats"]})
    assert response.status_code == 201
    scene = response.json()
    data = client.get(f"/api/scenes/{scene['id']}/data").json()
    assert set(data["modules"]) == {"stats"}
    assert set(data["raw"]["modules"]) == {"stats"}
    assert data["source"] == "demo" and data["warnings"]
    export = client.get(f"/api/scenes/{scene['id']}/export")
    assert export.status_code == 200
    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        assert {"index.html", "style.css", "overlay.js", "config.json", "data.json"} <= set(archive.namelist())
        assert set(json.loads(archive.read("data.json"))["modules"]) == {"stats"}
        assert json.loads(archive.read("config.json"))["connectedApiUrl"] is None
        assert b'fetch("data.json")' not in archive.read("overlay.js")
        assert b'"source":"demo"' in archive.read("index.html")
    assert client.delete(f"/api/scenes/{scene['id']}").status_code == 204
    assert client.get(f"/api/scenes/{scene['id']}").status_code == 404


def test_live_errors_are_not_replaced_by_demo(tmp_path):
    upstream = FotmobClient(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    client = TestClient(create_app(data_dir=tmp_path, client=upstream))
    result = client.post("/api/query", json={"kind": "team", "id": "1", "mode": "live"})
    assert result.status_code == 502
    assert result.json() == {"error": {"code": "ACCESS_DENIED", "message": "FotMob がアクセスを拒否しました。デモへ切り替えるか、時間をおいて再取得してください"}}


def test_live_filtered_raw_contains_only_selected_modules(tmp_path):
    upstream = FotmobClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=load_fixture("team_current.json"))))
    client = TestClient(create_app(data_dir=tmp_path, client=upstream))
    data = client.post("/api/query", json={"kind": "team", "id": "8455", "sections": ["squad"]}).json()
    assert set(data["modules"]) == {"squad"}
    assert data["raw"] == {"selected": data["modules"]}


def test_schema_objects_are_invalid_response_instead_of_renderer_children(tmp_path):
    upstream = FotmobClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"details": {"name": {"unexpected": 1}}})))
    client = TestClient(create_app(data_dir=tmp_path, client=upstream))
    response = client.post("/api/query", json={"kind": "team", "id": "1"})
    assert response.status_code == 502 and response.json()["error"]["code"] == "INVALID_RESPONSE"


def test_unrecognized_json_schema_is_not_a_successful_empty_query(tmp_path):
    upstream = FotmobClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"message": "different API"})))
    client = TestClient(create_app(data_dir=tmp_path, client=upstream))
    response = client.post("/api/query", json={"kind": "team", "id": "1"})
    assert response.status_code == 502 and response.json()["error"]["code"] == "INVALID_RESPONSE"


def test_export_escapes_script_delimiters_and_uses_safe_dom(tmp_path):
    scene = SceneInput(name="<script>", query=Query(kind="match", id="1", mode="demo")).model_dump()
    scene["id"] = "test"
    malicious = '</script><script>alert("x")</script>'
    data = {"source": "fotmob", "fetchedAt": "2026-10-07T00:00:00Z", "modules": {"team": {"name": malicious}}, "raw": {}, "warnings": [], "unavailable": []}
    with zipfile.ZipFile(io.BytesIO(make_export(scene, data, frontend_dist=tmp_path))) as archive:
        html = archive.read("index.html").decode()
        assert malicious not in html
        assert "\\u003c/script\\u003e" in html
        script = archive.read("overlay.js").decode()
        assert "textContent" in script and "innerHTML" not in script


def test_portable_export_uses_shared_frontend_renderer_when_available(tmp_path):
    portable = tmp_path / "export"
    portable.mkdir()
    (portable / "overlay-export.js").write_text("/* shared renderer */", encoding="utf-8")
    (portable / "style.css").write_text("/* shared CSS */", encoding="utf-8")
    scene = SceneInput(name="Test", query=Query(kind="team", id="1", mode="demo")).model_dump()
    with zipfile.ZipFile(io.BytesIO(make_export(scene, {"modules": {}}, frontend_dist=tmp_path))) as archive:
        assert b'id="root"' in archive.read("index.html")
        assert archive.read("overlay.js") == b"/* shared renderer */"


@pytest.mark.parametrize("change", [{"timezone": "Not/AZone"}, {"timeout": 0}, {"id": "../1"}, {"sections": ["unknown"]}])
def test_query_rejects_invalid_configuration(change):
    with pytest.raises(ValidationError):
        Query.model_validate({"kind": "team", "id": "8455", **change})


def test_css_and_layout_cannot_inject_or_leave_canvas():
    base = {"name": "Test", "query": {"kind": "team", "id": "1"}}
    for theme in ({"accent": "url(https://evil.example)"}, {"accent": "#12345"}):
        with pytest.raises(ValidationError):
            SceneInput.model_validate({**base, "theme": theme})
    with pytest.raises(ValidationError):
        SceneInput.model_validate({**base, "widgets": [{"id": "x", "section": "stats", "x": 1900, "y": 0, "width": 300, "height": 300}]})


def test_cors_is_same_origin_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.options("/api/scenes", headers={"Origin": "https://other.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in response.headers


def test_duplicate_scene_sections_cannot_diverge_preview_and_export():
    base = {"name": "Test", "query": {"kind": "team", "id": "1"}}
    with pytest.raises(ValidationError):
        SceneInput.model_validate({**base, "sections": ["stats", "stats"]})
    with pytest.raises(ValidationError):
        SceneInput.model_validate({**base, "widgets": [{"id": name, "section": "stats", "x": 0, "y": 0, "width": 100, "height": 100} for name in ["one", "two"]]})
