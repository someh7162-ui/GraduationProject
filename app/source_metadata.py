"""Provenance is supplied by an operator; importing does not verify a source."""
from datetime import datetime, time, timezone
from urllib.parse import urlsplit

SOURCE_FIELDS = ("source_type", "source_authority", "last_verified_at", "effective_from", "effective_to")
SOURCE_TYPES = {"unknown", "official_website", "official_document", "manual", "other"}


def timestamp(value, end=False):
    if not value:
        return None
    try:
        text = str(value)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if len(text) == 10 and end:
            parsed = datetime.combine(parsed.date(), time.max)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def normalize_source(row, existing=None):
    values = {key: (row[key] if key in row else (existing or {}).get(key)) for key in SOURCE_FIELDS}
    values["source_type"] = values["source_type"] or "unknown"
    # Legacy crawler categories describe a section, not verified authority.
    if values["source_type"] in {"校园新闻", "通知公告", "教务处通知"}:
        values["source_type"] = "unknown"
    if values["source_type"] not in SOURCE_TYPES:
        raise ValueError("Unsupported source_type")
    values["source_authority"] = str(values["source_authority"] or "").strip() or None
    if values["source_authority"] and len(values["source_authority"]) > 200:
        raise ValueError("source_authority exceeds 200 characters")
    for key in ("last_verified_at", "effective_from", "effective_to"):
        if values[key]:
            parsed = timestamp(values[key], end=key == "effective_to")
            if parsed is None:
                raise ValueError(f"Invalid {key}")
            values[key] = parsed.isoformat()
        else:
            values[key] = None
    if values["last_verified_at"] and timestamp(values["last_verified_at"]) > datetime.now(timezone.utc):
        raise ValueError("last_verified_at cannot be in the future")
    if values["effective_from"] and values["effective_to"] and timestamp(values["effective_from"]) > timestamp(values["effective_to"]):
        raise ValueError("effective_from must not exceed effective_to")
    return values


def content_active(content, at=None):
    at = at or datetime.now(timezone.utc)
    if content.get("status") != "published":
        return False
    for key, end in (("publish_time", False), ("effective_from", False), ("effective_to", True)):
        raw = content.get(key)
        parsed = timestamp(raw, end=end)
        if raw and parsed is None:
            return False
        if parsed and ((end and parsed < at) or (not end and parsed > at)):
            return False
    return True


def source_details(content):
    raw_url = content.get("source_url") or ""
    try:
        url = urlsplit(raw_url)
        safe_url = raw_url if url.scheme.lower() in {"http", "https"} and url.netloc and not url.username else None
    except ValueError:
        safe_url = None
    verified = timestamp(content.get("last_verified_at"))
    return {**{key: content.get(key) for key in SOURCE_FIELDS},
            "source_type": content.get("source_type") or "unknown",
            "verification_status": "recorded" if verified and verified <= datetime.now(timezone.utc) else "unverified",
            "source_department": content.get("source_department"), "source_site": content.get("source_site"),
            "source_url": safe_url, "publish_time": content.get("publish_time"), "updated_at": content.get("updated_at")}
