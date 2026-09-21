"""Import campus information from JSON/NDJSON/CSV/PDF into contents.

The PDF mode intentionally keeps the source document as a searchable record so
that historical summaries remain traceable even when individual article URLs
are unavailable.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import engine, contents, jt, now
from app.source_metadata import normalize_source
from app.content_types import normalize_type
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

TYPES = {
    "竞赛": "competition", "挑战杯": "competition", "大赛": "competition",
    "就业": "employment", "招聘": "employment", "双选会": "employment",
    "讲座": "lecture", "学术": "academic", "奖学金": "scholarship",
    "志愿": "volunteer", "社团": "club", "选课": "teaching", "教务": "teaching",
    "考试": "teaching", "课程": "teaching", "毕业": "graduate", "活动": "activity",
}

def classify(text: str) -> str:
    for key, typ in TYPES.items():
        if key in text: return typ
    return "notice"

def clean(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()

def pdf_record(path: Path) -> list[dict]:
    pages = None
    # The PDF uses a subset font that can make pypdf return replacement
    # characters. Prefer Poppler's cmap-aware extractor when available.
    if shutil.which("pdftotext"):
        try:
            proc = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(path), "-"],
                                  check=True, capture_output=True)
            raw = proc.stdout.decode("utf-8", errors="replace")
            pages = raw.split("\f")
        except (OSError, subprocess.SubprocessError):
            pages = None
    if pages is None:
        from pypdf import PdfReader
        pages = [(p.extract_text() or "") for p in PdfReader(str(path)).pages]
    out=[]
    for n,raw_page in enumerate(pages,1):
        text = clean(raw_page)
        if not text: continue
        out.append({"title": f"{path.stem}（第{n}页）", "body": text, "summary": text[:500],
            "content_type": classify(text), "tags": ["新疆工程学院", "公开信息", "校园新闻", "通知公告"],
            "source_url": "", "source_site": "新疆工程学院", "source_department": "新疆工程学院",
            "source_id": f"{path.name}#page={n}"})
    return out

def load(path: Path):
    if path.suffix.lower() == ".pdf": return pdf_record(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".ndjson", ".jsonl"): return [json.loads(x) for x in raw.splitlines() if x.strip()]
    obj = json.loads(raw); return obj if isinstance(obj, list) else obj.get("items", [obj])

def list_value(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith('['):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError('Expected list')
        return parsed
    return [x.strip() for x in re.split(r"[,，、]", str(value or "")) if x.strip()]


def import_records(rows):
    counts = dict(total=len(rows), added=0, updated=0, duplicate=0, failed=0)
    with engine.begin() as conn:
        for row in rows:
            try:
                # A bad record must not roll back successful records or leave
                # the transaction unusable after a database constraint failure.
                with conn.begin_nested():
                    source_id = clean(row.get('source_id'))
                    url = clean(row.get('source_url') or row.get('article_url') or row.get('source_page_url'))
                    existing = None
                    if source_id:
                        existing = conn.execute(select(contents).where(contents.c.source_id == source_id)).mappings().first()
                    elif url:
                        existing = conn.execute(select(contents).where(contents.c.source_url == url)).mappings().first()
                    old = dict(existing) if existing else {}
                    title = clean(row.get('title', old.get('title')))
                    body = clean(row.get('body') or row.get('content') or row.get('text') or old.get('body'))
                    if not title or not body:
                        raise ValueError('title/body required')
                    digest = hashlib.sha256((title + '\n' + body).encode('utf-8')).hexdigest()
                    values = dict(title=title, body=body, summary=clean(row.get('summary', old.get('summary'))) or body[:500],
                                  content_type=normalize_type(row.get('content_type') or old.get('content_type') or classify(title + body)),
                                  content_hash=digest, source_id=source_id or old.get('source_id') or '',
                                  source_url=url if any(k in row for k in ('source_url', 'article_url', 'source_page_url')) else old.get('source_url', ''),
                                  source_site=clean(row.get('source_site', old.get('source_site'))),
                                  source_department=clean(row.get('source_department', old.get('source_department'))),
                                  publish_time=row.get('publish_time') or row.get('date') or old.get('publish_time') or now(),
                                  end_time=row.get('end_time', old.get('end_time')),
                                  status=row.get('status', old.get('status', 'published')),
                                  **normalize_source(row, old))
                    if values['status'] not in {'published', 'draft', 'archived'}:
                        raise ValueError('Invalid content status')
                    for key in ('tags', 'target_roles', 'target_colleges', 'target_majors', 'target_grades'):
                        values[key] = jt(list_value(row.get(key, old.get(key, []))))
                    if old:
                        if all(old.get(key) == value for key, value in values.items()):
                            counts['duplicate'] += 1
                            continue
                        conn.execute(update(contents).where(contents.c.id == old['id']).values(**values, updated_at=now()))
                        counts['updated'] += 1
                    else:
                        if conn.execute(select(contents.c.id).where(contents.c.content_hash == digest)).first():
                            counts['duplicate'] += 1
                            continue
                        conn.execute(contents.insert().values(**values, crawl_time=now(), updated_at=now()))
                        counts['added'] += 1
            except IntegrityError:
                counts['duplicate'] += 1
            except Exception as exc:
                print(f'skip: {exc}', file=sys.stderr)
                counts['failed'] += 1
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    args = parser.parse_args()
    print(json.dumps(import_records(load(Path(args.input))), ensure_ascii=False))


if __name__ == '__main__':
    main()
