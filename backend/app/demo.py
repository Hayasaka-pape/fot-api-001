"""Explicit, fictional demonstration data. Never used as a live fallback."""
import copy
from datetime import datetime, timezone

from .models import Query
from .normalizers import KIND_SECTIONS

HOME_NAMES = ["Robert Sánchez", "Reece James", "Wesley Fofana", "Levi Colwill", "Marc Cucurella", "Moisés Caicedo", "Enzo Fernández", "Cole Palmer", "Pedro Neto", "João Pedro", "Liam Delap"]
AWAY_NAMES = ["Gianluigi Donnarumma", "Rico Lewis", "Rúben Dias", "Joško Gvardiol", "Rayan Aït-Nouri", "Rodri", "Tijjani Reijnders", "Phil Foden", "Bernardo Silva", "Jérémy Doku", "Erling Haaland"]


def demo_response(query: Query):
    kickoff = f"{query.date or '2026-10-07'}T21:00:00+09:00"
    home = {"id": 8455, "name": "Chelsea", "shortName": "CHE", "score": 2}
    away = {"id": 8456, "name": "Manchester City", "shortName": "MCI", "score": 1}
    fixture = {"id": query.id or "5315746", "home": home["name"], "away": away["name"], "homeScore": 2, "awayScore": 1, "status": "LIVE", "kickoff": kickoff, "league": "DEMO • Premier League"}
    def players(names):
        return [{"name": name, "shirtNumber": number, "position": "GK" if index == 0 else "DF" if index < 5 else "MF" if index < 8 else "FW"} for index, (name, number) in enumerate(zip(names, [1, 24, 29, 6, 3, 25, 8, 10, 7, 20, 9]))]
    all_modules = {
        "scoreboard": {"home": home, "away": away, "league": "DEMO • Premier League", "status": "LIVE", "clock": "67′", "kickoff": kickoff},
        "stats": [{"label": label, "home": left, "away": right} for label, left, right in [("ボール支配率", "54%", "46%"), ("シュート", 14, 9), ("枠内シュート", 6, 3), ("期待得点 (xG)", "1.82", "0.94"), ("コーナーキック", 5, 3), ("ファウル", 8, 10)]],
        "lineup": {"home": {"name": "Chelsea", "formation": "4-2-3-1", "players": players(HOME_NAMES)}, "away": {"name": "Manchester City", "formation": "4-3-3", "players": players(AWAY_NAMES)}},
        "fixtures": [fixture, {**fixture, "id": "5181855", "home": "Arsenal", "away": "Liverpool", "homeScore": None, "awayScore": None, "status": "試合前"}, {**fixture, "id": "5181856", "home": "Brighton", "away": "Newcastle", "homeScore": 1, "awayScore": 1, "status": "FT"}],
        "standings": [{"position": index + 1, "team": name, "played": 7, "won": won, "drawn": drawn, "lost": 7-won-drawn, "goalsFor": gf, "goalsAgainst": ga, "goalDifference": gf-ga, "points": won*3+drawn} for index, (name, won, drawn, gf, ga) in enumerate([("Arsenal", 6, 1, 18, 4), ("Manchester City", 5, 1, 17, 7), ("Liverpool", 5, 0, 15, 6), ("Chelsea", 4, 2, 14, 8), ("Tottenham", 4, 1, 13, 9), ("Newcastle", 3, 2, 10, 9)])],
        "team": {"name": "Chelsea", "country": "ENG", "coach": "デモ監督", "venue": "Stamford Bridge"},
        "league": {"name": "Premier League", "country": "ENG", "season": "2026/2027 (DEMO)"},
        "squad": players(HOME_NAMES),
    }
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
