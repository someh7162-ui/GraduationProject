"""Pure recommendation scoring shared by the API and offline evaluation."""
import json
import math
from app.source_metadata import content_active
from app.content_types import normalize_type, CONTENT_TYPES
from datetime import datetime, timezone

BEHAVIOR_WEIGHTS = {"view": 0.1, "click": 0.2, "favorite": 0.6,
                    "share": 0.7, "register": 1.0, "dismiss": -0.8}
SCORE_WEIGHTS = {"content": 0.55, "profile": 0.20, "freshness": 0.15, "urgency": 0.10}
STRATEGIES = ("interest", "identity", "hybrid")


def array(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return value if isinstance(value, list) else []


def date(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except ValueError:
        return None


def content_visible(user, content):
    for field, values in (
        ("target_roles", [user.get("role")]),
        ("target_grades", [user.get("grade")]),
        ("target_colleges", [user.get("college"), user.get("college_code")]),
        ("target_majors", [user.get("major"), user.get("major_code")]),
    ):
        targets = set(array(content.get(field)))
        if targets and not targets.intersection(v for v in values if v):
            return False
    return True


def behavior_profile(user, contents, events, at):
    # The latest event of each type on each article counts once. Repeated clicks
    # cannot outweigh a favorite simply by accumulating duplicate requests.
    visible = {c["id"]: c for c in contents
               if c.get("status") == "published" and content_visible(user, c)}
    latest = {}
    for event in events:
        if event.get("user_id") != user["id"] or event.get("event_type") not in BEHAVIOR_WEIGHTS:
            continue
        timestamp = date(event.get("timestamp"))
        if timestamp is None or timestamp > at or event.get("content_id") not in visible:
            continue
        key = (event["content_id"], event["event_type"])
        latest[key] = max(timestamp, latest.get(key, timestamp))
    profile = {}
    for (content_id, kind), timestamp in latest.items():
        age = (at - timestamp).total_seconds() / 86400
        weight = BEHAVIOR_WEIGHTS[kind] * 0.5 ** (age / 30)
        for tag in set(array(visible[content_id].get("tags"))):
            profile[tag] = profile.get(tag, 0.0) + weight
    return {tag: math.tanh(weight) for tag, weight in profile.items()}


def rank_contents(user, contents, events, *, at=None, strategy="hybrid"):
    if strategy not in STRATEGIES:
        raise ValueError("Unknown recommendation strategy")
    at = at or datetime.now(timezone.utc)
    interests = set(array(user.get("interests")))
    profile = behavior_profile(user, contents, events, at)
    ranked = []
    for row in contents:
        if not content_active(row, at) or not content_visible(user, row):
            continue
        published, end = date(row.get("publish_time")), date(row.get("end_time"))
        if (published and published > at) or (end and end < at):
            continue
        tags = set(array(row.get("tags")))
        matched = sorted(interests & tags)
        interest = len(matched) / max(1, len(interests))
        identity = sum(bool(array(row.get(key))) for key in
                       ("target_colleges", "target_majors", "target_grades")) / 3
        content = 0.85 * interest + 0.15 * identity
        behavior = sum(profile.get(tag, 0.0) for tag in tags) / max(1, len(tags))
        freshness = max(0.0, 1 - (at - published).total_seconds() / (365 * 86400)) if published else 0.0
        days = (end - at).total_seconds() / 86400 if end else None
        urgency = 1.0 if days is not None and days <= 1 else 0.7 if days is not None and days <= 3 else 0.0
        details = dict(content=content, profile=behavior, freshness=freshness, urgency=urgency)
        score = interest if strategy == "interest" else content if strategy == "identity" else max(0.0, sum(SCORE_WEIGHTS[k] * v for k, v in details.items()))
        reasons = []
        if matched:
            reasons.append("兴趣匹配：" + "、".join(matched))
        if strategy != "interest" and identity:
            reasons.append("符合你的学院、专业或年级范围")
        if strategy == "hybrid":
            if behavior > 0:
                reasons.append("近期互动偏好加分")
            elif behavior < 0:
                reasons.append("已根据不感兴趣反馈降权")
            if urgency:
                reasons.append("即将截止")
        item = dict(row)
        item["content_type"] = normalize_type(item.get("content_type"))
        item["content_type_label"] = CONTENT_TYPES[item["content_type"]]
        for key in ("tags", "target_roles", "target_colleges", "target_majors", "target_grades"):
            item[key] = array(item.get(key))
        item.update(score=round(score, 4), reason="；".join(reasons) or "为你补充可访问的校园信息",
                    matched_tags=matched, score_detail={**{k: round(v, 4) for k, v in details.items()},
                    "interest": round(interest, 4), "identity": round(identity, 4)},
                    deadline=row.get("end_time"), days_remaining=math.ceil(days) if days is not None else None,
                    deadline_status="today" if urgency == 1 else "ending_soon" if urgency else "normal")
        ranked.append((score, item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [item for _, item in ranked]


def match_summary(items, k=10):
    top = items[:k]
    matched = sum(bool(item["matched_tags"]) for item in top)
    return {"top_k": k, "sample_size": len(top), "matched_count": matched,
            "interest_match_rate": round(matched / len(top), 4) if top else None}
