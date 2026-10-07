import copy
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.demo import demo_response
from app.main import create_app
from app.models import Query
from app.normalizers import normalize


def member(identity, name=None, **extra):
    return {"id": identity, "name": name or f"Player {identity}", "shirtNumber": identity, "position": "MF", **extra}


def source(events=None, *, started=True, finished=False):
    return {
        "general": {"matchId": "1234", "started": started, "finished": finished,
                    "homeTeam": {"name": "Home", "id": 101}, "awayTeam": {"name": "Away", "id": 102}},
        "header": {"status": {"started": started, "finished": finished}},
        "content": {"lineup": {
            "homeTeam": {"name": "Home", "formation": "4-3-3", "starters": [member(i) for i in (1, 2, 3)], "subs": [member(i) for i in range(4, 10)]},
            "awayTeam": {"name": "Away", "formation": "4-4-2", "starters": [member(i) for i in (11, 12, 13)], "subs": [member(i) for i in (14, 15)]},
        }, "matchFacts": {"events": {"events": events or []}}},
    }


def substitution(incoming, outgoing, minute, added=0, *, home=True, **extra):
    return {"type": "Substitution", "swap": [{"id": str(incoming)}, {"id": str(outgoing)}],
            "time": minute, "overloadTime": added, "isHome": home, **extra}


def red_card(identity, minute=60, *, home=True, **extra):
    return {"type": "Card", "card": "YellowRed", "player": {"id": identity}, "time": minute, "isHome": home, **extra}


def lineup(raw):
    return normalize(raw, Query(kind="match", id="1234", sections=["lineup"]))[0]["lineup"]


def identities(team):
    return {player["id"] for player in team["players"]}


@pytest.mark.parametrize("match_id,home_count,away_count", [("5315746", 11, 11), ("5181855", 10, 11)])
def test_unmodified_real_rosters_events_and_dismissal(match_id, home_count, away_count):
    raw = json.loads((Path(__file__).parent / "fixtures" / f"match_on_pitch_{match_id}.json").read_text("utf-8"))
    value = lineup(raw)
    assert value["view"] == "onPitch" and value["state"] == "final"
    assert value["warnings"] == []
    assert value["home"]["tracking"] == value["away"]["tracking"] == "current"
    assert len(value["home"]["players"]) == home_count
    assert len(value["away"]["players"]) == away_count
    assert len(value["home"]["startingPlayers"]) == 11
    if match_id == "5315746":
        assert "843040" in identities(value["home"]) and "873289" not in identities(value["home"])
        assert "1113903" in identities(value["home"]) and "807729" not in identities(value["home"])
        assert next(player for player in value["away"]["players"] if player["id"] == "1104053")["enteredAt"] == "46′"
    else:
        assert "163670" not in identities(value["home"])  # Real Perišić YellowRed at 79.
        assert "1382000" in identities(value["home"]) and "31097" not in identities(value["home"])
        assert "574645" in identities(value["away"]) and "942372" not in identities(value["away"])


def test_substitute_can_be_substituted_again_and_added_time_orders_before_next_period():
    events = [substitution(4, 1, 45, 8), substitution(5, 4, 46), substitution(6, 5, 90, 8),
              substitution(7, 6, 91), substitution(8, 7, 105, 2), substitution(9, 8, 106)]
    value = lineup(source(list(reversed(events)), finished=True))
    assert value["state"] == "final"
    assert identities(value["home"]) == {"9", "2", "3"}
    assert next(player for player in value["home"]["players"] if player["id"] == "9")["enteredAt"] == "106′"
    assert {player["id"] for player in value["home"]["startingPlayers"]} == {"1", "2", "3"}


def test_simultaneous_substitutions_and_duplicate_source_events_are_idempotent():
    first = substitution(4, 1, 67)
    value = lineup(source([substitution(5, 2, 67), first, copy.deepcopy(first)]))
    assert value["state"] == "live" and identities(value["home"]) == {"4", "5", "3"}
    assert [player.get("enteredAt") for player in value["home"]["players"][:2]] == ["67′", "67′"]


def test_unknown_team_can_only_be_resolved_by_unique_registered_player_ids():
    event = substitution(4, 1, 60)
    event.pop("isHome")
    assert identities(lineup(source([event]))["home"]) == {"4", "2", "3"}


@pytest.mark.parametrize("event", [
    red_card(4),
    red_card(999, cardDescription={"localizedKey": "coach", "defaultText": "Coach"}),
])
def test_registered_bench_and_explicit_coach_dismissals_do_not_reduce_pitch_players(event):
    value = lineup(source([event]))
    assert value["state"] == "live" and identities(value["home"]) == {"1", "2", "3"}


def test_a_card_to_a_subbed_out_player_at_the_same_minute_is_not_a_pitch_dismissal():
    value = lineup(source([substitution(4, 1, 65), red_card(1, 65)]))
    assert value["state"] == "live" and identities(value["home"]) == {"4", "2", "3"}


def test_pitch_dismissal_removes_player_without_a_fictional_replacement():
    value = lineup(source([red_card(2)]))
    assert identities(value["home"]) == {"1", "3"}
    assert len(value["home"]["startingPlayers"]) == 3


@pytest.mark.parametrize("event", [
    substitution(99, 1, 67), substitution("", 1, 67), substitution(4, 1, "unknown"),
    substitution(4, 1, 1, period="SecondHalf"), substitution(4, 1, 67, period={"unknown": 2}),
    red_card(999), red_card(1, cardDescription={"localizedKey": "bench"}),
])
def test_unknown_ids_clocks_roles_and_periods_cannot_be_claimed_as_current(event):
    value = lineup(source([event]))
    assert value["state"] == "uncertain"
    assert value["home"]["tracking"] == "uncertain" and value["home"]["players"] == []
    assert len(value["home"]["startingPlayers"]) == 3
    assert value["away"]["tracking"] == "current"
    assert value["warnings"]


@pytest.mark.parametrize("event", [substitution(4, 1, 67, cancelled=True), red_card(1, VAR={"decision": "unknown"})])
def test_unverified_cancellation_and_var_forms_are_not_guessed_or_reapplied(event):
    raw = source([event])
    # A remaining marker must never override an unknown cancellation status.
    raw["content"]["lineup"]["homeTeam"]["starters"][0]["performance"] = {"substitutionEvents": [{"type": "subOut", "time": 67}]}
    value = lineup(raw)
    assert value["state"] == "uncertain" and value["home"]["players"] == []
    assert value["home"]["startingPlayers"][0]["id"] == "1"
    assert any("取消" in warning for warning in value["warnings"])


def test_each_snapshot_is_rebuilt_from_the_starting_roster_after_a_timeline_correction():
    raw = source([substitution(4, 1, 67)])
    assert identities(lineup(raw)["home"]) == {"4", "2", "3"}
    raw["content"]["matchFacts"]["events"]["events"] = []
    assert identities(lineup(raw)["home"]) == {"1", "2", "3"}


def test_performance_markers_only_detect_missing_timeline_and_never_invent_pairings():
    raw = source([])
    raw["content"]["lineup"]["homeTeam"]["starters"][0]["performance"] = {"substitutionEvents": [{"type": "subOut", "time": 60}]}
    raw["content"]["lineup"]["homeTeam"]["subs"][0]["performance"] = {"substitutionEvents": [{"type": "subIn", "time": 60}]}
    value = lineup(raw)
    assert value["state"] == "uncertain" and value["home"]["players"] == []
    assert any("不足" in warning for warning in value["warnings"])
    raw["content"]["lineup"]["homeTeam"]["starters"][0]["performance"] = {"events": [{"type": "secondYellow"}]}
    assert lineup(raw)["home"]["tracking"] == "uncertain"


def test_live_missing_timeline_keeps_source_starters_without_claiming_them_as_current():
    raw = source()
    del raw["content"]["matchFacts"]
    value = lineup(raw)
    assert value["state"] == "uncertain"
    assert value["home"]["players"] == [] and len(value["home"]["startingPlayers"]) == 3
    _, warnings, _ = normalize(raw, Query(kind="match", id="1234", sections=["scoreboard"]))
    assert warnings == []  # Warnings from unrequested lineup never leak into other selections.


def test_starting_and_unavailable_states_are_explicit():
    raw = source(started=False)
    del raw["content"]["matchFacts"]
    value = lineup(raw)
    assert value["state"] == "starting"
    assert value["home"]["tracking"] == "starting" and len(value["home"]["players"]) == 3
    del raw["content"]["lineup"]
    modules, warnings, unavailable = normalize(raw, Query(kind="match", id="1234", sections=["lineup"]))
    assert modules["lineup"]["state"] == "unavailable" and unavailable == ["lineup"]
    assert warnings


@pytest.mark.parametrize("change", ["missing_id", "duplicate_id", "too_many", "shared_id"])
def test_missing_duplicate_and_oversized_rosters_cannot_produce_a_current_list(change):
    raw = source()
    home = raw["content"]["lineup"]["homeTeam"]
    if change == "missing_id":
        home["starters"][0].pop("id")
    elif change == "duplicate_id":
        home["starters"][1]["id"] = 1
    elif change == "too_many":
        home["starters"] = [member(i) for i in range(20, 32)]
    else:
        home["starters"][0]["id"] = 11
    value = lineup(raw)
    assert value["state"] == "uncertain" and value["home"]["players"] == []
    assert value["home"]["startingPlayers"]


def test_demo_live_current_list_differs_from_source_starters_and_contains_substitution_times():
    result = demo_response(Query(kind="match", id="5315746", mode="demo", sections=["lineup"]))
    value = result["modules"]["lineup"]
    assert result["source"] == "demo" and result["warnings"]
    assert value["state"] == "live" and value["home"]["formationSource"] == "starting"
    assert len(value["home"]["players"]) == len(value["home"]["startingPlayers"]) == 11
    assert "9000002" not in identities(value["home"]) and "9000021" in identities(value["home"])
    assert next(player for player in value["home"]["players"] if player["id"] == "9000021")["enteredAt"] == "46′"
    assert next(player for player in value["away"]["players"] if player["id"] == "9001021")["enteredAt"] == "64′"


def test_preexisting_saved_lineup_scene_and_export_follow_subsequent_provider_snapshots(tmp_path):
    class Provider:
        raw = source([])
        async def fetch(self, query):
            return copy.deepcopy(self.raw), "2026-10-07T00:00:00Z"
    provider = Provider()
    client = TestClient(create_app(data_dir=tmp_path / "data", client=provider, frontend_dist=tmp_path / "no-dist"))
    scene = client.post("/api/scenes", json={"name": "Existing lineup scene", "query": {"kind": "match", "id": "1234", "mode": "live"}, "sections": ["lineup"]}).json()
    endpoint = f"/api/scenes/{scene['id']}"
    assert identities(client.get(endpoint + "/data").json()["modules"]["lineup"]["home"]) == {"1", "2", "3"}
    provider.raw = source([substitution(4, 1, 67)])
    updated = client.get(endpoint + "/data").json()
    assert identities(updated["modules"]["lineup"]["home"]) == {"4", "2", "3"}
    assert set(updated["modules"]) == {"lineup"}
    with zipfile.ZipFile(io.BytesIO(client.get(endpoint + "/export").content)) as archive:
        exported = json.loads(archive.read("data.json"))
        assert exported["modules"]["lineup"] == updated["modules"]["lineup"]
        assert exported["modules"]["lineup"]["view"] == "onPitch"
        script = archive.read("overlay.js").decode()
        assert "現在の出場選手を確認できません" in script and "先発登録配置" in script
