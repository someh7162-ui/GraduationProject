"""Copy legacy SQLite rows into a configured MySQL database.

The script is intentionally conservative: it copies only rows whose target
tables are empty and leaves the legacy SQLite file untouched.
"""
import os
import sqlite3
from pathlib import Path
from app.main import engine, init_db, users, contents, events, feedbacks
from app.catalog.xjie_academics import resolve_student_selection

source = Path(os.getenv("CAMPUS_DB", Path(__file__).resolve().parents[1] / "campus.db"))
if not engine.url.get_backend_name().startswith("mysql"):
    raise SystemExit("请先配置 MYSQL_PASSWORD 或 DATABASE_URL 为 MySQL")
init_db()
if not source.exists():
    raise SystemExit(f"SQLite 文件不存在: {source}")
with sqlite3.connect(source) as old, engine.begin() as new:
    old.row_factory = sqlite3.Row
    for table, columns in [(users, ["id", "name", "role", "college", "college_code", "major", "major_code", "grade", "interests", "created_at"]), (contents, ["id", "title", "body", "content_type", "publisher_id", "target_roles", "target_colleges", "target_majors", "target_grades", "tags", "summary", "source_url", "source_site", "source_department", "source_id", "content_hash", "crawl_time", "updated_at", "source_type", "source_authority", "last_verified_at", "effective_from", "effective_to", "start_time", "end_time", "publish_time", "status"]), (events, ["id", "user_id", "content_id", "event_type", "source", "timestamp"]), (feedbacks, ["id", "user_id", "content_id", "feedback_type", "reason", "created_at"])]:
        if new.execute(table.select().limit(1)).first():
            continue
        legacy_columns = {row[1] for row in old.execute(f"PRAGMA table_info({table.name})")}
        available = [column for column in columns if column in legacy_columns]
        if not available:
            continue
        rows = old.execute(f"SELECT {','.join(available)} FROM {table.name}").fetchall()
        if rows:
            payload = [dict(row) for row in rows]
            if table is users:
                for record in payload:
                    if not record.get("college_code") or not record.get("major_code"):
                        try:
                            college, major = resolve_student_selection(record.get("college"), record.get("major"))
                        except ValueError:
                            continue
                        record.update(college=college["name"], college_code=college["code"],
                                      major=major["name"], major_code=major["code"])
            new.execute(table.insert(), payload)
            print(f"migrated {table.name}: {len(rows)}")
print("Migration complete")
