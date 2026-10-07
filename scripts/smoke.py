"""Exercise the running Docker application without third-party dependencies."""
import argparse
import io
import json
import urllib.error
import urllib.request
import zipfile


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

    assert request("/api/health")
    for kind in ("match", "date", "team", "league"):
        result = request("/api/query", {
            "kind": kind, "id": "5315746" if kind == "match" else "47",
            "date": "2026-10-07", "mode": "demo", "timezone": "Asia/Tokyo", "timeout": 10,
        })
        assert result["source"] == "demo", result
        assert result["modules"], kind
        assert result["fetchedAt"]
        print(f"PASS demo query: {kind}")

    query = {"kind": "match", "id": "5315746", "mode": "demo", "timezone": "Asia/Tokyo", "timeout": 10}
    payload = {
        "name": "Docker smoke scene", "query": query, "sections": ["scoreboard", "stats"],
        "canvas": {"width": 1920, "height": 1080, "background": "transparent"},
        "theme": {"accent": "#36e3b0", "background": "#101822", "text": "#ffffff", "opacity": .95},
        "widgets": [
            {"id": "scoreboard", "section": "scoreboard", "x": 48, "y": 48, "width": 1100, "height": 220, "fontSize": 24},
            {"id": "stats", "section": "stats", "x": 48, "y": 300, "width": 500, "height": 650, "fontSize": 22},
        ], "pollInterval": 30,
    }
    scene = request("/api/scenes", payload)
    scene_id = scene["id"]
    try:
        assert request(f"/api/scenes/{scene_id}")["name"] == payload["name"]
        payload["name"] = "Docker smoke updated"
        assert request(f"/api/scenes/{scene_id}", payload, "PUT")["name"] == payload["name"]
        assert any(item["id"] == scene_id for item in request("/api/scenes"))
        result = request(f"/api/scenes/{scene_id}/data")
        assert set(result["modules"]) <= {"scoreboard", "stats"}, result["modules"].keys()
        assert "scoreboard" in result["modules"]
        html = request(f"/overlay/{scene_id}")
        assert b"<html" in html and b"<script" in html
        with zipfile.ZipFile(io.BytesIO(request(f"/api/scenes/{scene_id}/export"))) as archive:
            required = {"index.html", "style.css", "overlay.js", "data.json", "config.json"}
            assert required <= set(archive.namelist()), archive.namelist()
            exported = json.loads(archive.read("data.json"))
            assert set(exported["modules"]) <= {"scoreboard", "stats"}
            assert json.loads(archive.read("config.json"))["canvas"]["width"] == 1920
        print("PASS scene CRUD, selected JSON, OBS route, HTML/CSS/JS/JSON export")
    finally:
        request(f"/api/scenes/{scene_id}", method="DELETE")

    try:
        request("/api/query", {"kind": "date", "mode": "live", "date": "invalid", "timezone": "Asia/Tokyo"})
    except urllib.error.HTTPError as error:
        assert error.code in (400, 422), error.code
        assert "error" in json.loads(error.read())
    else:
        raise AssertionError("Invalid dates must be rejected")
    assert b"<html" in request("/")
    print("PASS validation and frontend delivery")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    run(parser.parse_args().base_url)
