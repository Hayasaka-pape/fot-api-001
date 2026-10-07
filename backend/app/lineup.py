"""Reconstruct players on the pitch from verified FotMob roster/timeline IDs.

Observed schema: matchFacts.events.events, Substitution.swap=[IN, OUT],
Card.card=Red/YellowRed. Performance summaries only detect incomplete timelines;
they never invent changes or pair two players by their names or shirt numbers.
"""
import re
from collections import Counter

from .values import as_list, as_object


def player_id(value):
    if isinstance(value, bool):
        return None
    value = str(value) if isinstance(value, (str, int)) else ""
    return value if re.fullmatch(r"[1-9][0-9]{0,11}", value) else None


def event_clock(event):
    """Clock labels are ordered as (base minute, added minute), not their sum.

    45+8 is before minute 46; 90+8 is before extra-time minute 91.
    """
    def parse(value):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return None
        match = re.fullmatch(r"\s*(\d{1,3})(?:\s*\+\s*(\d{1,2}))?[′']?\s*", str(value))
        return (int(match[1]), int(match[2] or 0)) if match else None
    clock = parse(event.get("time")) or parse(event.get("timeStr"))
    if clock is None or clock[0] > 150:
        return None
    added = event.get("overloadTime")
    if added is None:
        added = event.get("addedTime")
    if added is not None:
        if isinstance(added, bool) or not re.fullmatch(r"\+?\d{1,2}", str(added)):
            return None
        clock = (clock[0], int(str(added).lstrip("+")))
    elif clock[1] == 0:
        label = parse(event.get("timeStr"))
        if label and label[0] == clock[0]:
            clock = label
    return clock


def entered_label(clock):
    return f"{clock[0]}{f'+{clock[1]}' if clock[1] else ''}′"


def phase(raw):
    general = as_object(raw.get("general"))
    status = as_object(as_object(raw.get("header")).get("status"))
    if general.get("finished") is True or status.get("finished") is True:
        return "final"
    if general.get("started") is True or status.get("started") is True:
        return "live"
    if general.get("started") is False or status.get("started") is False:
        return "starting"
    return "uncertain"


def track_lineup(raw, normalize_player):
    content = as_object(raw.get("content"))
    lineup = as_object(content.get("lineup"))
    general = as_object(raw.get("general"))
    result = {"view": "onPitch", "state": phase(raw), "warnings": []}
    registries, current, issues, summary_players = {}, {}, {}, {}
    available = {}
    for side in ("home", "away"):
        team = as_object(lineup.get(f"{side}Team")) or as_object(lineup.get(side))
        starters = as_list(team.get("starters", team.get("players")))
        # Dropping unnamed starter entries would silently turn a damaged XI into
        # a supposedly verified 10-player side. Retain the source baseline and
        # mark it uncertain instead of inferring a missing player's dismissal.
        registry, baseline, side_issues = {}, [], []
        roster = starters + as_list(team.get("subs"))
        for member_index, member in enumerate(roster):
            member = as_object(member)
            identity = player_id(member.get("id"))
            normalized = {**normalize_player(member), "id": identity}
            if member_index < len(starters):
                baseline.append(normalized)
                if not isinstance(normalized["name"], str) or not normalized["name"].strip():
                    side_issues.append("先発選手の名前がありません")
            if identity:
                if identity in registry:
                    side_issues.append("登録選手の ID が重複しています")
                registry[identity] = normalized
        identities = [member["id"] for member in baseline]
        if baseline and any(identity is None for identity in identities):
            side_issues.append("先発選手の ID がありません")
        if len(baseline) > 11:
            side_issues.append("先発名簿が 11 人を超えています")
        name = team.get("name") or as_object(general.get(f"{side}Team")).get("name")
        result[side] = {"name": name, "formation": team.get("formation"), "formationSource": "starting",
                        "tracking": "starting" if result["state"] == "starting" and baseline else "uncertain",
                        "players": [dict(member) for member in baseline] if result["state"] == "starting" else [],
                        "startingPlayers": baseline}
        registries[side], current[side], issues[side] = registry, identities, side_issues
        summary_players[side], available[side] = roster, bool(baseline)
        if not baseline:
            issues[side].append("先発名簿が取得できません")
    if set(registries["home"]) & set(registries["away"]):
        for side in issues:
            issues[side].append("両チームの選手 ID が重複しています")
    if result["state"] == "starting":
        if not all(available.values()):
            result["state"] = "unavailable" if not any(available.values()) else "uncertain"
        return finish(result, issues, current, registries, preserve_starting=True)
    if not any(available.values()):
        result["state"] = "unavailable"
        return finish(result, issues, current, registries)
    if result["state"] == "uncertain":
        for side in issues:
            issues[side].append("試合の開始・終了状態が取得できません")
    container = as_object(as_object(content.get("matchFacts")).get("events"))
    events = container.get("events")
    # An absent timeline is not an empty timeline: displaying starters as current
    # would falsely claim that no substitutions or dismissals have occurred.
    if not isinstance(events, list):
        for side in issues:
            issues[side].append("交代・退場の時系列イベントが取得できません")
        return finish(result, issues, current, registries)

    def infer_side(event, identities):
        if isinstance(event.get("isHome"), bool):
            return "home" if event["isHome"] else "away"
        candidates = [side for side in registries if identities and all(identity in registries[side] for identity in identities if identity)]
        return candidates[0] if len(candidates) == 1 else None

    def issue(side, message):
        for target in ([side] if side else ["home", "away"]):
            issues[target].append(message)

    changes = []
    for index, event in enumerate(events):
        event = as_object(event)
        kind = event.get("type")
        swap = as_list(event.get("swap"))
        identities = [player_id(as_object(member).get("id")) for member in swap]
        identity = player_id(as_object(event.get("player")).get("id") or event.get("playerId"))
        side = infer_side(event, identities if kind == "Substitution" else [identity] if identity else [])
        if kind == "VAR":
            issue(side, "VAR の変更内容を交代・退場情報として確認できません")
            continue
        red = kind == "Card" and event.get("card") in ("Red", "YellowRed")
        if kind != "Substitution" and not red:
            # Ignoring a red marker just because its event type changed would
            # claim the player stayed on the pitch. Unknown card/change forms
            # must invalidate tracking rather than be treated as harmless text.
            if (kind == "Card" and event.get("card") != "Yellow") or event.get("card") in ("Red", "YellowRed") or (kind != "Comment" and any(identities)):
                issue(side, "未対応の選手変更イベントがあります")
            continue
        # No cancellation variant was observed in the source fixtures. Do not
        # decide that an unverified reversal/VAR flag means a valid dismissal.
        reversal_keys = ("cancelled", "canceled", "isCancelled", "isCanceled", "deleted", "isDeleted", "VAR")
        if any(event.get(key) not in (None, False) for key in reversal_keys):
            issue(side, "交代・退場の取消または VAR 情報の形式を確認できません")
            continue
        clock = event_clock(event)
        if clock is None:
            issue(side, "交代・退場の時刻がありません")
            continue
        period = event.get("period")
        period_floor = {"FirstHalf": 0, "SecondHalf": 46, "FirstExtraHalf": 91, "SecondExtraHalf": 106,
                        "ExtraFirstHalf": 91, "ExtraSecondHalf": 106}.get(period) if isinstance(period, str) else None
        if period is not None and (period_floor is None or clock[0] < period_floor):
            issue(side, "交代・退場の期間と時刻の形式を確認できません")
            continue
        if side is None:
            issue(None, "交代・退場のチームを ID で特定できません")
            continue
        if kind == "Substitution":
            if len(identities) != 2 or any(identity is None for identity in identities):
                issue(side, "交代する選手の ID がありません")
                continue
        elif identity is None:
            issue(side, "退場する選手の ID がありません")
            continue
        changes.append((clock, index, side, kind, identities if kind == "Substitution" else [identity], event))

    seen, observed = set(), {side: Counter() for side in registries}
    red_seen, dismissed = {side: set() for side in registries}, {side: set() for side in registries}
    used = {side: set(current[side]) for side in registries}
    for clock, index, side, kind, identities, event in sorted(changes, key=lambda change: (change[0], change[1])):
        fingerprint = (clock, side, kind, tuple(identities))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        active, registry = current[side], registries[side]
        if kind == "Substitution":
            incoming, outgoing = identities
            if incoming not in registry or outgoing not in registry:
                issue(side, "交代選手の ID が登録名簿と一致しません")
                continue
            if not isinstance(registry[incoming]["name"], str) or not registry[incoming]["name"].strip():
                issue(side, "交代出場する選手の名前がありません")
                continue
            if outgoing not in active or incoming in used[side] or incoming in dismissed[side]:
                issue(side, "交代イベントと現在の出場選手が一致しません")
                continue
            active[active.index(outgoing)] = incoming
            used[side].add(incoming)
            registry[incoming] = {**registry[incoming], "enteredAt": entered_label(clock)}
            observed[side][(incoming, "subIn")] += 1
            observed[side][(outgoing, "subOut")] += 1
        else:
            identity = identities[0]
            description = as_object(event.get("cardDescription"))
            bench_role = description.get("localizedKey") in ("coach", "bench", "substitute", "substitutes")
            if bench_role and identity in active:
                issue(side, "退場選手のピッチ・ベンチ区分が一致しません")
                continue
            if identity not in registry and not bench_role:
                issue(side, "退場選手の ID が登録名簿と一致しません")
                continue
            red_seen[side].add(identity)
            dismissed[side].add(identity)
            if identity in active:
                active.remove(identity)
            # Removing every red-card recipient would incorrectly reduce the XI
            # for bench/subbed-out players or an identified coach.

    # Summary markers do not provide verified IN/OUT pairings or dismissal order;
    # replaying them could double-apply or resurrect a corrected timeline event.
    for side, roster in summary_players.items():
        expected = Counter()
        for member in roster:
            member = as_object(member)
            identity = player_id(member.get("id"))
            performance = as_object(member.get("performance"))
            if performance.get("substitutionEvents") is not None and not isinstance(performance["substitutionEvents"], list):
                issue(side, "交代要約の形式を確認できません")
            for event in as_list(performance.get("substitutionEvents")):
                event = as_object(event)
                if event.get("type") in ("subIn", "subOut"):
                    expected[(identity, event["type"])] += 1
                else:
                    issue(side, "交代要約の形式を確認できません")
            for event in as_list(performance.get("events")):
                if as_object(event).get("type") in ("redCard", "secondYellow") and identity not in red_seen[side]:
                    issue(side, "退場の時系列イベントが不足しています")
        if any(observed[side][change] < count for change, count in expected.items()):
            issue(side, "交代の時系列イベントが不足しています")
    return finish(result, issues, current, registries)


def finish(result, issues, current, registries, preserve_starting=False):
    for side in ("home", "away"):
        team = result[side]
        if issues[side] and not (preserve_starting and team["startingPlayers"] and all(reason == "先発選手の ID がありません" for reason in issues[side])):
            team["tracking"] = "uncertain"
            # Keeping a best-effort roster here would look like verified current
            # players. Retain startingPlayers for reference, but show no guessed XI.
            team["players"] = []
            reason = " / ".join(dict.fromkeys(issues[side]))
            result["warnings"].append(f"{team['name'] or side}: 現在の出場選手を確定できません（{reason}）。")
        elif not preserve_starting:
            team["tracking"] = "current"
            team["players"] = [dict(registries[side][identity]) for identity in current[side]]
    if result["state"] != "unavailable" and any(team["tracking"] == "uncertain" for team in (result["home"], result["away"])):
        result["state"] = "uncertain"
    return result
