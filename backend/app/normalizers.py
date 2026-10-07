"""Only normalize values that are present in the upstream response."""
import re
from collections import Counter
from datetime import datetime, timezone as UTC
from zoneinfo import ZoneInfo

from .errors import InvalidResponseError
from .lineup import track_lineup
from .models import Query

KIND_SECTIONS = {
    "match": ["scoreboard", "stats", "lineup", "fixtures", "standings"],
    "date": ["fixtures"],
    "team": ["team", "fixtures", "squad", "standings", "stats"],
    "league": ["league", "standings", "fixtures", "stats"],
}


def obj(value):
    return value if isinstance(value, dict) else {}


def items(value):
    return value if isinstance(value, list) else []


def local_time(value, timezone):
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC.utc)
        return stamp.astimezone(ZoneInfo(timezone)).isoformat()
    except ValueError:
        return value


def status_text(status, general=None):
    status, general = obj(status), obj(general)
    reason = status.get("reason")
    if isinstance(reason, dict) and (reason.get("short") or reason.get("long")):
        return reason.get("short") or reason.get("long")
    if isinstance(reason, str) and reason:
        return reason
    if status.get("cancelled"):
        return "中止"
    if status.get("finished") or general.get("finished"):
        return "FT"
    if status.get("started") or general.get("started"):
        return "LIVE"
    return "試合前"


def scores(status, home, away):
    # scoreStr is the regulation/extra-time result; some endpoints store shootout
    # totals in home.score, so use scoreStr when both are present.
    match = re.fullmatch(r"\s*(\d+)\s*[-–:]\s*(\d+)\s*", str(obj(status).get("scoreStr", "")))
    return (int(match[1]), int(match[2])) if match else (obj(home).get("score"), obj(away).get("score"))


def fixture(match, league, timezone, league_id=None, league_country=None):
    match = obj(match)
    home, away, status = obj(match.get("home")), obj(match.get("away")), obj(match.get("status"))
    if not home.get("name") or not away.get("name"):
        return None
    home_score, away_score = scores(status, home, away)
    value = {"id": str(match.get("id", "")), "home": home["name"], "away": away["name"],
            "homeScore": home_score, "awayScore": away_score, "status": status_text(status),
            "kickoff": local_time(status.get("utcTime"), timezone),
            "league": obj(match.get("tournament")).get("name") or league}
    if league_id is not None:
        value["leagueId"] = str(league_id)
    if league_country:
        value["leagueCountry"] = league_country
    return value


def extract_fixtures(raw, kind, timezone):
    fixtures = []
    if kind == "date":
        if not isinstance(raw.get("leagues"), list):
            return None
        for league in raw["leagues"]:
            for match in items(obj(league).get("matches")):
                # id distinguishes tournament stages/groups. primaryId identifies
                # their shared parent and must only be used if the group ID is absent.
                league_id = obj(league).get("id") or obj(league).get("primaryId") or obj(match).get("leagueId")
                league_country = obj(league).get("ccode") or obj(league).get("countryCode")
                value = fixture(match, obj(league).get("name"), timezone, league_id, league_country)
                if value:
                    fixtures.append(value)
        return fixtures
    data = obj(raw.get("fixtures"))
    candidates = data.get("allMatches")
    if candidates is None:
        candidates = obj(data.get("allFixtures")).get("fixtures")
    if candidates is None:
        candidates = data.get("fixtures")
    if candidates is None:
        return None
    for match in items(candidates):
        value = fixture(match, obj(raw.get("details")).get("name") if kind == "league" else None, timezone)
        if value:
            fixtures.append(value)
    return fixtures


def match_options(data):
    """Group only selectable, identified matches; never group by display name."""
    groups = {}
    skipped = 0
    for match in data["modules"].get("fixtures", []):
        league_id, match_id, name = match.get("leagueId"), match.get("id"), match.get("league")
        if (not league_id or not name or not re.fullmatch(r"[0-9]{1,12}", str(league_id))
                or not re.fullmatch(r"[0-9]{1,12}", str(match_id or ""))):
            skipped += 1
            continue
        league_id = str(league_id)
        if league_id not in groups:
            groups[league_id] = {"id": league_id, "name": name, "matches": [], "_country": match.get("leagueCountry")}
        groups[league_id]["matches"].append({**match, "id": str(match_id), "leagueId": league_id})
    # Preserve the original fixture league labels while making same-name
    # dropdown options distinguishable to a human, not just to the UI's keys.
    name_counts = Counter(group["name"] for group in groups.values())
    country_counts = Counter((group["name"], group["_country"]) for group in groups.values())
    for group in groups.values():
        name, country = group["name"], group.pop("_country")
        if name_counts[name] > 1:
            group["name"] = f"{name} · {country}" if country else name
            if not country or country_counts[(name, country)] > 1:
                group["name"] += f" · ID {group['id']}"
    warnings = list(data["warnings"])
    if skipped:
        warnings.append(f"ID・リーグ名が取得できない {skipped} 試合は選択候補に含めていません。")
    return {"source": data["source"], "fetchedAt": data["fetchedAt"],
            "leagues": list(groups.values()), "warnings": warnings}


def table_rows(node):
    """Pick the all/home-away-independent standings, including composite groups."""
    if isinstance(node, list):
        rows = []
        for item in node:
            rows.extend(table_rows(item))
        return rows
    if not isinstance(node, dict):
        return []
    if isinstance(node.get("all"), list):
        return node["all"]
    rows = []
    for key in ("data", "table", "tables"):
        if key in node:
            rows.extend(table_rows(node[key]))
    return rows


def extract_standings(raw):
    rows = table_rows(raw.get("table")) or table_rows(obj(raw.get("overview")).get("table")) or table_rows(obj(raw.get("content")).get("table"))
    output, seen = [], set()
    for row in rows:
        row = obj(row)
        key = row.get("id") or row.get("name")
        if not row.get("name") or key in seen:
            continue
        seen.add(key)
        goals = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", str(row.get("scoresStr", "")))
        output.append({"position": row.get("idx", row.get("position")), "team": row["name"],
                       "played": row.get("played"), "won": row.get("wins"), "drawn": row.get("draws"),
                       "lost": row.get("losses"), "goalsFor": int(goals[1]) if goals else row.get("goalsFor"),
                       "goalsAgainst": int(goals[2]) if goals else row.get("goalsAgainst"),
                       "goalDifference": row.get("goalConDiff", row.get("goalDifference")), "points": row.get("pts", row.get("points"))})
    return output or None


def player(value, fallback_position=None):
    value = obj(value)
    position = value.get("position") or value.get("positionIdsDesc") or obj(value.get("role")).get("fallback") or fallback_position
    if position is None and value.get("usualPlayingPositionId") is not None:
        position = {0: "GK", 1: "DF", 2: "MF", 3: "FW"}.get(value["usualPlayingPositionId"])
    return {"name": value.get("name") or obj(value.get("player")).get("name"),
            "shirtNumber": value.get("shirtNumber"), "position": position}


def extract_lineup(raw):
    return track_lineup(raw, player)


def extract_stats(raw):
    data = obj(obj(raw.get("content")).get("stats"))
    groups = items(obj(obj(data.get("Periods")).get("All")).get("stats"))
    result, seen = [], set()
    for group in groups:
        for row in items(obj(group).get("stats")):
            row = obj(row)
            values = row.get("stats")
            key = row.get("key") or row.get("title")
            if key in seen or row.get("type") == "title" or not isinstance(values, list) or len(values) != 2 or values == [None, None]:
                continue
            seen.add(key)
            label = row.get("title") or key
            if row.get("key") in ("BallPossesion", "ball_possession"):
                values = [f"{value}%" if value is not None else None for value in values]
            result.append({"label": label, "home": values[0], "away": values[1]})
    return result or None


def extract_season_stats(raw, kind):
    data = obj(raw.get("stats"))
    result, seen = [], set()
    for group in ("teams", "players"):
        for stat in items(data.get(group)):
            stat = obj(stat)
            participants = items(stat.get("topThree")) if kind == "league" else [obj(stat.get("participant"))]
            if not participants:
                participants = [obj(stat.get("participant"))]
            for participant in participants:
                participant = obj(participant)
                details = obj(participant.get("stat"))
                value = details.get("value", participant.get("value"))
                name = participant.get("name")
                if value is None or not name:
                    continue
                label = stat.get("header") or details.get("name")
                if not label:
                    continue
                # Name makes league leader rows and individual player rows unambiguous.
                if kind == "league" or group == "players":
                    label = f"{label} · {name}"
                key = (label, name)
                if key in seen:
                    continue
                seen.add(key)
                if details.get("format") == "percent":
                    value = f"{value}%"
                result.append({"label": label, "home": value, "away": None})
    return result or None


def extract_scoreboard(raw, timezone):
    general, header = obj(raw.get("general")), obj(raw.get("header"))
    home, away = obj(general.get("homeTeam")), obj(general.get("awayTeam"))
    teams = items(header.get("teams"))
    if len(teams) >= 2:
        home = {**home, **obj(teams[0])}
        away = {**away, **obj(teams[1])}
    if not home.get("name") or not away.get("name"):
        return None
    status = obj(header.get("status"))
    home_score, away_score = scores(status, home, away)
    home = {"id": home.get("id"), "name": home["name"], "shortName": home.get("shortName", home["name"]), "score": home_score}
    away = {"id": away.get("id"), "name": away["name"], "shortName": away.get("shortName", away["name"]), "score": away_score}
    clock = header.get("liveTime") or status.get("liveTime") or obj(raw.get("ongoing")).get("time")
    if isinstance(clock, dict):
        clock = clock.get("short") or clock.get("time")
    return {"home": home, "away": away, "league": general.get("leagueName"), "status": status_text(status, general),
            "clock": clock, "kickoff": local_time(status.get("utcTime") or general.get("matchTimeUTCDate"), timezone)}


def normalize(raw: dict, query: Query):
    if query.kind == "date" and not isinstance(raw.get("leagues"), list):
        raise InvalidResponseError("FotMob の日付別応答に leagues がありません")
    if query.kind in ("team", "league") and not obj(raw.get("details")).get("name"):
        raise InvalidResponseError("FotMob の応答にチーム・大会の details がありません")
    if query.kind == "match" and not obj(raw.get("general")):
        raise InvalidResponseError("FotMob の試合応答に general がありません")
    modules = {}
    if query.kind == "match":
        for key, value in (("scoreboard", extract_scoreboard(raw, query.timezone)), ("stats", extract_stats(raw)), ("lineup", extract_lineup(raw))):
            if value is not None:
                modules[key] = value
        scoreboard = modules.get("scoreboard")
        if scoreboard:
            modules["fixtures"] = [{"id": str(obj(raw.get("general")).get("matchId", query.id)),
                                    "home": scoreboard["home"]["name"], "away": scoreboard["away"]["name"],
                                    "homeScore": scoreboard["home"]["score"], "awayScore": scoreboard["away"]["score"],
                                    "status": scoreboard["status"], "kickoff": scoreboard["kickoff"], "league": scoreboard["league"]}]
    else:
        fixtures = extract_fixtures(raw, query.kind, query.timezone)
        if fixtures is not None:
            modules["fixtures"] = fixtures
        season_stats = extract_season_stats(raw, query.kind)
        if season_stats is not None:
            modules["stats"] = season_stats
    standings = extract_standings(raw)
    if standings is not None:
        modules["standings"] = standings
    details = obj(raw.get("details"))
    if query.kind == "team" and details.get("name"):
        groups = items(obj(raw.get("squad")).get("squad"))
        coach, squad = None, []
        for group in groups:
            members = items(obj(group).get("members"))
            if obj(group).get("title") == "coach":
                coach = next((obj(item).get("name") for item in members if obj(item).get("name")), None)
            else:
                squad.extend(player(item) for item in members if obj(item).get("name"))
        venue = obj(obj(details.get("sportsTeamJSONLD")).get("location")).get("name")
        info = obj(obj(raw.get("overview")).get("teamInfo"))
        modules["team"] = {"name": details["name"], "country": details.get("country"),
                           "coach": coach or obj(info.get("coach")).get("name"), "venue": venue or obj(info.get("stadium")).get("name")}
        if squad:
            modules["squad"] = squad
    if query.kind == "league" and details.get("name"):
        modules["league"] = {"name": details["name"], "country": details.get("country"),
                             "season": details.get("selectedSeason") or details.get("latestSeason")}
    requested = query.sections if query.sections is not None else KIND_SECTIONS[query.kind]
    unavailable = [section for section in requested if section not in modules]
    modules = {key: value for key, value in modules.items() if key in requested}
    warnings = []
    if "lineup" in modules:
        warnings.extend(modules["lineup"]["warnings"])
        if modules["lineup"]["state"] == "unavailable" and "lineup" not in unavailable:
            unavailable.append("lineup")
    if unavailable:
        warnings.append("取得できない項目: " + ", ".join(unavailable) + "。試合前・大会の収録範囲・応答形式によって取得できる項目が変わります。")
    validate_modules(modules)
    return modules, warnings, unavailable


def validate_modules(modules):
    """Reject object/list values where the browser renderer expects plain text."""
    def scalar(value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (str, int, float))):
            raise TypeError("invalid normalized scalar")
    for section, value in modules.items():
        if section == "scoreboard":
            for side in ("home", "away"):
                for field in ("id", "name", "shortName", "score"):
                    scalar(value[side][field])
            for field in ("league", "status", "clock", "kickoff"):
                scalar(value[field])
        elif section == "lineup":
            for side in ("home", "away"):
                scalar(value[side]["name"])
                scalar(value[side]["formation"])
                for member in value[side]["players"] + value[side]["startingPlayers"]:
                    for field in member.values():
                        scalar(field)
        elif isinstance(value, list):
            for row in value:
                for field in row.values():
                    scalar(field)
        else:
            for field in value.values():
                scalar(field)
