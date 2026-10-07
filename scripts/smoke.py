"""Exercise the running Docker application without third-party dependencies."""
import argparse
import io
import json
import urllib.error
import urllib.request
import zipfile


# These are deliberately fictional IDs, not live player IDs that would change across seasons.
def assert_current_demo_players(lineup):
    """The 67-minute demo includes known substitutions, with initial XI kept."""
    assert lineup["view"] == "onPitch", lineup
    assert lineup["state"] == "live", lineup
    substitutions = {
        "home": [
            ("9000002", "Reece James", "9000021", "Malo Gusto", "46′"),
            ("9000009", "Pedro Neto", "9000022", "Alejandro Garnacho", "62′"),
        ],
        "away": [
            ("9001009", "Bernardo Silva", "9001021", "Rayan Cherki", "64′"),
        ],
    }
    for side, changes in substitutions.items():
        team = lineup[side]
        assert team["tracking"] == "current", team
        assert team["formationSource"] == "starting", team
        assert len(team["players"]) == len(team["startingPlayers"]) == 11, team
        current = {str(player["id"]): player for player in team["players"]}
        starting = {str(player["id"]): player for player in team["startingPlayers"]}
        assert len(current) == len(starting) == 11, team
        for out_id, out_name, in_id, in_name, entered_at in changes:
            assert out_id in starting and starting[out_id]["name"] == out_name, team
            assert out_id not in current, (out_name, current)
            assert in_id in current and current[in_id]["name"] == in_name, team
            assert in_id not in starting, (in_name, starting)
            assert current[in_id]["enteredAt"] == entered_at, current[in_id]


def run(base_url: str) -> None:
    base_url = base_url.rstrip("/")

    def request(path, payload=None, method=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            base_url + path, data=body, method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read()
            if "application/json" in response.headers.get("Content-Type", ""):
                return json.loads(content)
            return content

    assert request("/api/health")["status"] == "ok"
    options = request("/api/match-options", {
        "date": "2026-10-07", "mode": "demo", "timezone": "Asia/Tokyo", "timeout": 10,
    })
    assert options["source"] == "demo", options
    assert options["fetchedAt"]
    leagues = options["leagues"]
    assert isinstance(leagues, list) and len(leagues) >= 2, leagues
    league_ids, match_ids = set(), set()
    for league in leagues:
        league_id = str(league["id"])
        assert league_id and league_id not in league_ids, league
        league_ids.add(league_id)
        assert league["name"] and league["matches"], league
        for match in league["matches"]:
            match_id = str(match["id"])
            assert match_id and match_id not in match_ids, match
            match_ids.add(match_id)
            assert str(match["leagueId"]) == league_id, (league, match)
            assert match["home"] and match["away"], match
        # Choosing a match in another league must retrieve that match, rather
        # than keep a fixed demo scoreboard from the initial selection.
        selected = league["matches"][0]
        details = request("/api/query", {
            "kind": "match", "id": str(selected["id"]), "date": "2026-10-07",
            "mode": "demo", "timezone": "Asia/Tokyo", "timeout": 10,
            "sections": ["scoreboard"],
        })
        assert details["source"] == "demo", details
        assert set(details["modules"]) == {"scoreboard"}, details["modules"].keys()
        scoreboard = details["modules"]["scoreboard"]
        assert scoreboard["home"]["name"] == selected["home"], (selected, scoreboard)
        assert scoreboard["away"]["name"] == selected["away"], (selected, scoreboard)
    print("PASS date/league/match choices, league grouping and selected match details")

    try:
        request("/api/match-options", {
            "date": "2026-02-30", "mode": "demo", "timezone": "Asia/Tokyo", "timeout": 10,
        })
    except urllib.error.HTTPError as error:
        assert error.code == 422, error.code
        detail = json.loads(error.read())
        assert detail["error"]["code"] == "VALIDATION_ERROR", detail
    else:
        raise AssertionError("Invalid match-options dates must be rejected with HTTP 422")
    print("PASS match-options calendar date validation")

    demo_lineup = None
    expected_modules = {"match": "scoreboard", "date": "fixtures", "team": "team", "league": "league"}
    for kind in ("match", "date", "team", "league"):
        result = request("/api/query", {
            "kind": kind, "id": "5315746" if kind == "match" else "47",
            "date": "2026-10-07", "mode": "demo", "timezone": "Asia/Tokyo", "timeout": 10,
        })
        assert result["source"] == "demo", result
        assert result["kind"] == kind, result
        assert result["modules"], kind
        assert expected_modules[kind] in result["modules"], (kind, result["modules"])
        assert result["fetchedAt"]
        if kind == "match":
            demo_lineup = result["modules"]["lineup"]
            assert_current_demo_players(demo_lineup)
        print(f"PASS demo query: {kind}")
    print("PASS substitutions remove outgoing players, add incoming players and retain initial XI")

    query = {"kind": "match", "id": "5315746", "mode": "demo", "timezone": "Asia/Tokyo", "timeout": 10}
    payload = {
        "name": "Docker smoke scene", "query": query, "sections": ["scoreboard", "stats", "lineup"],
        "canvas": {"width": 1920, "height": 1080, "background": "transparent"},
        "theme": {"accent": "#36e3b0", "background": "#101822", "text": "#ffffff", "opacity": .95},
        "widgets": [
            {"id": "scoreboard", "section": "scoreboard", "x": 48, "y": 48, "width": 1100, "height": 220, "fontSize": 24},
            {"id": "stats", "section": "stats", "x": 48, "y": 300, "width": 500, "height": 650, "fontSize": 22},
            {"id": "lineup", "section": "lineup", "x": 600, "y": 300, "width": 1200, "height": 650, "fontSize": 22},
        ], "pollInterval": 30,
    }
    scene = request("/api/scenes", payload)
    scene_id = scene["id"]
    selected_sections = set(payload["sections"])
    try:
        assert request(f"/api/scenes/{scene_id}")["name"] == payload["name"]
        payload["name"] = "Docker smoke updated"
        assert request(f"/api/scenes/{scene_id}", payload, "PUT")["name"] == payload["name"]
        assert any(item["id"] == scene_id for item in request("/api/scenes"))
        result = request(f"/api/scenes/{scene_id}/data")
        # Demo provides every requested module; accepting a subset would hide missing saved data.
        assert set(result["modules"]) == selected_sections, result["modules"].keys()
        assert "scoreboard" in result["modules"]
        assert_current_demo_players(result["modules"]["lineup"])
        assert result["modules"]["lineup"] == demo_lineup
        html = request(f"/overlay/{scene_id}")
        assert b"<html" in html and b"<script" in html
        with zipfile.ZipFile(io.BytesIO(request(f"/api/scenes/{scene_id}/export"))) as archive:
            required = {"index.html", "style.css", "overlay.js", "data.json", "config.json"}
            assert required <= set(archive.namelist()), archive.namelist()
            exported = json.loads(archive.read("data.json"))
            assert set(exported["modules"]) == selected_sections, exported["modules"].keys()
            assert_current_demo_players(exported["modules"]["lineup"])
            assert exported["modules"]["lineup"] == result["modules"]["lineup"]
            assert json.loads(archive.read("config.json"))["snapshot"] is True
            assert json.loads(archive.read("config.json"))["canvas"]["width"] == 1920
        print("PASS scene CRUD, selected JSON, OBS route and snapshot export retain current players")
    finally:
        # A failed export must not leave a temporary test scene in the user's normal collection.
        request(f"/api/scenes/{scene_id}", method="DELETE")

    try:
        # Invalid live input must be rejected before any dependency on the upstream service.
        request("/api/query", {"kind": "date", "mode": "live", "date": "invalid", "timezone": "Asia/Tokyo"})
    except urllib.error.HTTPError as error:
        assert error.code == 422, error.code
        detail = json.loads(error.read())
        assert detail["error"]["code"] == "VALIDATION_ERROR", detail
    else:
        raise AssertionError("Invalid dates must be rejected")
    assert b"<html" in request("/")
    print("PASS validation and frontend delivery")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    run(parser.parse_args().base_url)
