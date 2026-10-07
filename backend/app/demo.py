"""Explicit, fictional demonstration data. Never used as a live fallback."""
import copy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .models import Query
from .normalizers import KIND_SECTIONS

HOME_NAMES = ["Robert Sánchez", "Reece James", "Wesley Fofana", "Levi Colwill", "Marc Cucurella", "Moisés Caicedo", "Enzo Fernández", "Cole Palmer", "Pedro Neto", "João Pedro", "Liam Delap"]
AWAY_NAMES = ["Gianluigi Donnarumma", "Rico Lewis", "Rúben Dias", "Joško Gvardiol", "Rayan Aït-Nouri", "Rodri", "Tijjani Reijnders", "Phil Foden", "Bernardo Silva", "Jérémy Doku", "Erling Haaland"]

DEMO_MATCHES = [
    {"id": "5315746", "home": "Chelsea", "homeId": 8455, "homeShort": "CHE", "away": "Manchester City", "awayId": 8456, "awayShort": "MCI", "homeScore": 2, "awayScore": 1, "status": "LIVE", "clock": "67′", "leagueId": "47", "league": "DEMO • Premier League", "hour": 21},
    {"id": "5181855", "home": "Arsenal", "homeId": 9825, "homeShort": "ARS", "away": "Liverpool", "awayId": 8650, "awayShort": "LIV", "homeScore": None, "awayScore": None, "status": "試合前", "clock": None, "leagueId": "47", "league": "DEMO • Premier League", "hour": 23},
    {"id": "5181856", "home": "Brighton", "homeId": 10204, "homeShort": "BHA", "away": "Newcastle", "awayId": 10261, "awayShort": "NEW", "homeScore": 1, "awayScore": 1, "status": "FT", "clock": None, "leagueId": "47", "league": "DEMO • Premier League", "hour": 19},
    {"id": "9900001", "home": "Real Madrid", "homeId": 8633, "homeShort": "RMA", "away": "Bayern München", "awayId": 9823, "awayShort": "BAY", "homeScore": 3, "awayScore": 2, "status": "FT", "clock": None, "leagueId": "42", "league": "DEMO • Champions League", "hour": 18},
    {"id": "9900002", "home": "Paris Saint-Germain", "homeId": 9847, "homeShort": "PSG", "away": "Inter", "awayId": 8636, "awayShort": "INT", "homeScore": None, "awayScore": None, "status": "試合前", "clock": None, "leagueId": "42", "league": "DEMO • Champions League", "hour": 22},
]


def demo_response(query: Query):
    date = query.date or "2026-10-07"
    # The fictional daily schedule is defined in the requested timezone so a
    # selected demo match's date and kickoff remain consistent with its details.
    def kickoff_for(match):
        return datetime.fromisoformat(f"{date}T{match['hour']:02}:00:00").replace(tzinfo=ZoneInfo(query.timezone)).isoformat()
    selected = next((match for match in DEMO_MATCHES if match["id"] == query.id), DEMO_MATCHES[0])
    kickoff = kickoff_for(selected)
    home = {"id": selected["homeId"], "name": selected["home"], "shortName": selected["homeShort"], "score": selected["homeScore"]}
    away = {"id": selected["awayId"], "name": selected["away"], "shortName": selected["awayShort"], "score": selected["awayScore"]}
    fixtures = [{key: match[key] for key in ("id", "home", "away", "homeScore", "awayScore", "status", "league", "leagueId")} | {"kickoff": kickoff_for(match)} for match in DEMO_MATCHES]
    def players(names):
        return [{"name": name, "shirtNumber": number, "position": "GK" if index == 0 else "DF" if index < 5 else "MF" if index < 8 else "FW"} for index, (name, number) in enumerate(zip(names, [1, 24, 29, 6, 3, 25, 8, 10, 7, 20, 9]))]
    all_modules = {
        "scoreboard": {"home": home, "away": away, "league": selected["league"], "status": selected["status"], "clock": selected["clock"], "kickoff": kickoff},
        "stats": [{"label": label, "home": left, "away": right} for label, left, right in [("ボール支配率", "54%", "46%"), ("シュート", 14, 9), ("枠内シュート", 6, 3), ("期待得点 (xG)", "1.82", "0.94"), ("コーナーキック", 5, 3), ("ファウル", 8, 10)]],
        "lineup": {"home": {"name": home["name"], "formation": "4-2-3-1", "players": players(HOME_NAMES if selected["id"] == "5315746" else [f"デモ HOME 選手 {number}" for number in range(1, 12)])}, "away": {"name": away["name"], "formation": "4-3-3", "players": players(AWAY_NAMES if selected["id"] == "5315746" else [f"デモ AWAY 選手 {number}" for number in range(1, 12)])}},
        "fixtures": fixtures,
        "standings": [{"position": index + 1, "team": name, "played": 7, "won": won, "drawn": drawn, "lost": 7-won-drawn, "goalsFor": gf, "goalsAgainst": ga, "goalDifference": gf-ga, "points": won*3+drawn} for index, (name, won, drawn, gf, ga) in enumerate([("Arsenal", 6, 1, 18, 4), ("Manchester City", 5, 1, 17, 7), ("Liverpool", 5, 0, 15, 6), ("Chelsea", 4, 2, 14, 8), ("Tottenham", 4, 1, 13, 9), ("Newcastle", 3, 2, 10, 9)])],
        "team": {"name": "Chelsea", "country": "ENG", "coach": "デモ監督", "venue": "Stamford Bridge"},
        "league": {"name": "Premier League", "country": "ENG", "season": "2026/2027 (DEMO)"},
        "squad": players(HOME_NAMES),
    }
    if query.kind == "match":
        all_modules["fixtures"] = [match for match in fixtures if match["leagueId"] == selected["leagueId"]]
    elif query.kind == "team":
        all_modules["fixtures"] = [match for match in fixtures if match["leagueId"] == "47"]
    elif query.kind == "league" and query.id in ("42", "47"):
        all_modules["fixtures"] = [match for match in fixtures if match["leagueId"] == query.id]
        all_modules["league"]["name"] = "Champions League" if query.id == "42" else "Premier League"
    supported = KIND_SECTIONS[query.kind]
    if query.kind in ("team", "league"):
        all_modules["stats"] = [{"label": label, "home": value, "away": None} for label, value in [("1 試合平均得点", "2.0"), ("1 試合平均失点", "1.14"), ("平均支配率", "54%"), ("最多得点 · デモ選手", 5), ("最多アシスト · デモ選手", 3)]]
    requested = query.sections if query.sections is not None else supported
    modules = {key: copy.deepcopy(value) for key, value in all_modules.items() if key in requested and key in supported}
    unavailable = [key for key in requested if key not in modules]
    warnings = ["デモデータです。実際の試合結果・順位・選手情報ではありません。"]
    if unavailable:
        warnings.append("この検索形式に対応しない項目: " + ", ".join(unavailable))
    return {"source": "demo", "fetchedAt": datetime.now(timezone.utc).isoformat(), "kind": query.kind, "modules": modules, "raw": {"demo": True, "modules": copy.deepcopy(modules)}, "warnings": warnings, "unavailable": unavailable}
