"""Merge the 291 canonical PDF records with crawled list/article data.

The summary PDF (新疆工程学院公开校内信息汇总) declares 291 campus items:
241 校园新闻 + 34 通知公告 + 16 教务通知 over 2025-09-09..2026-09-09.  The
legacy data/xju_records.ndjson holds those 291 rows (title/date/category/
source_type/source_page_url) but no bodies.  This script joins each row with
the *live public website* crawl results (data/crawl/lists_*.ndjson for the
article URLs, data/crawl/articles_*.ndjson for the fetched bodies) and writes
one import-ready record per campus item -- never one record per PDF page.

Usage:

    python scripts/build_campus_dataset.py [--records data/xju_records.ndjson] \\
        [--out data/xju_enriched.ndjson]

Output schema (accepted by scripts/import_campus_data.py):

    date, title, body, summary, content_type, tags, category, source_type,
    source_url (article page), source_page_url (section list page),
    source_site="新疆工程学院", source_department,
    target_colleges/target_majors/target_grades=[], body_source
"""
from __future__ import annotations
import argparse, json, re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE_MIN, DATE_MAX = "2025-09-09", "2026-09-09"

_TYPE_RULES: list[tuple[str, list[str]]] = [
    ("competition", ["挑战杯", "竞赛", "大赛", "比赛", "获奖", "喜报", "夺冠", "一等奖",
                     "二等奖", "三等奖", "跆拳道", "锦标赛", "赛"]),
    ("employment", ["招聘", "双选会", "就业", "选调", "人才引进", "录用", "聘用",
                    "面向社会公开", "笔试成绩", "资格审查", "拟聘用", "考核成绩"]),
    ("scholarship", ["奖学金", "助学金", "评优"]),
    ("lecture", ["讲座", "大讲堂", "宣讲", "报告会", "论坛", "辅导", "培训"]),
    ("academic", ["科研", "学术", "研究", "实验室", "项目申报", "课题", "论证会", "论文"]),
    ("teaching", ["选课", "补考", "考试", "教学", "教务", "学籍", "转专业", "课程",
                  "开课", "实践教学", "实习", "毕业设计", "教材", "重修"]),
    ("graduate", ["毕业", "学位", "考研", "专升本"]),
    ("volunteer", ["志愿", "招募志愿者", "西部计划"]),
    ("club", ["社团", "招新"]),
    ("activity", ["活动", "仪式", "运动会", "晚会", "汇演", "联谊", "游学", "开放日",
                  "出征", "社会实践"]),
    ("notice", ["通知", "公告", "公示", "通报", "公开"]),
]
_MODULE_TAGS = {
    "competition": ["创新创业", "学习成长"], "employment": ["就业实习"],
    "scholarship": ["奖助学金"], "lecture": ["学习成长", "校园生活"],
    "academic": ["学习成长", "创新创业"], "teaching": ["学习成长"],
    "graduate": ["考研升学", "就业实习"], "volunteer": ["志愿服务"],
    "club": ["社团活动"], "activity": ["活动运营", "校园生活"],
    "notice": [], "news": [],
}
_SOURCE_CT = {"通知公告": "notice", "教务处通知": "teaching", "教务通知": "teaching",
              "校园新闻": "news"}


def norm(s: str) -> str:
    return re.sub(r"[\s…\u3000]+", "", s or "")


def clean_title(s: str) -> str:
    """Join PDF line wraps without destroying meaningful Latin/number spaces."""
    title = re.sub(r"\s+", " ", s or "").strip()
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", title)


def classify(title: str, body: str, source_type: str) -> str:
    text = title + "\n" + (body or "")[:200]
    for typ, kws in _TYPE_RULES:
        if any(k in text for k in kws):
            return typ
    return _SOURCE_CT.get(source_type, "news")


def derive_tags(title: str, category: str, source_type: str, content_type: str) -> list[str]:
    tags: list[str] = []
    if category:
        tags.append(category)
    if source_type in ("通知公告", "教务处通知", "教务通知"):
        tags.append("通知公告")
    for extra in _MODULE_TAGS.get(content_type, []):
        if extra not in tags:
            tags.append(extra)
    for kw, tag in [("新生", "新生入学"), ("军训", "新生入学"), ("奖学金", "奖助学金"),
                    ("志愿", "志愿服务"), ("社团", "社团活动"), ("就业", "就业实习"),
                    ("考研", "考研升学"), ("心理", "心理健康"), ("竞赛", "创新创业"),
                    ("大赛", "创新创业"), ("挑战杯", "创新创业")]:
        if kw in title and tag not in tags:
            tags.append(tag)
    return tags


def load_ndjson(p: Path) -> list[dict]:
    if not p.exists():
        return []
    # Some crawl exports (notably the notice list) include a UTF-8 BOM.
    return [json.loads(x) for x in p.read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def title_match(pdf_norm: str, site_norm: str) -> bool:
    """Site list titles may be truncated with '…'; accept an exact match or a
    long-enough prefix match (>=18 chars)."""
    if pdf_norm == site_norm:
        return True
    if len(site_norm) >= 18 and pdf_norm.startswith(site_norm):
        return True
    if len(pdf_norm) >= 18 and site_norm.startswith(pdf_norm):
        return True
    return False


def index_rows(rows: list[dict], key: str) -> dict:
    idx: dict[tuple, dict] = {}
    for r in rows:
        idx.setdefault((r.get("date"), norm(r.get("title", "")), key), r)
        idx.setdefault((r.get("date"), norm(r.get("title", "")), "*"), r)
    return idx


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", default=str(ROOT / "data/xju_records.ndjson"))
    ap.add_argument("--out", default=str(ROOT / "data/xju_enriched.ndjson"))
    args = ap.parse_args()

    crawl_dir = ROOT / "data/crawl"
    list_rows = load_ndjson(crawl_dir / "lists_news.ndjson") + \
        load_ndjson(crawl_dir / "lists_news_part1.ndjson") + \
        load_ndjson(crawl_dir / "lists_news_part2.ndjson") + \
        load_ndjson(crawl_dir / "lists_tzgg.ndjson") + \
        load_ndjson(crawl_dir / "lists_jwc.ndjson")
    list_by_title = {}
    for r in list_rows:
        list_by_title.setdefault((r.get("date"), norm(r.get("title", ""))), r)
    # long-prefix index for truncated site titles
    list_prefix: list[tuple] = [(r.get("date"), norm(r.get("title", ""))) for r in list_rows]
    articles_by_url: dict[str, dict] = {}
    articles_by_title: dict[tuple, dict] = {}
    for p in crawl_dir.glob("articles_*.ndjson"):
        for r in load_ndjson(p):
            articles_by_url[r.get("url")] = r
            articles_by_title.setdefault((r.get("date"), norm(r.get("title", ""))), r)

    records = load_ndjson(Path(args.records))
    out_rows: list[dict] = []
    unmatched: list[str] = []
    for rec in records:
        date = rec.get("date", "")
        title = clean_title(rec.get("title", ""))
        n = norm(title)
        if not title or not n:
            unmatched.append(f"{date} <empty title>")
            continue
        crawl = list_by_title.get((date, n))
        if crawl is None:
            for cand in list_prefix:
                if cand[0] == date and title_match(n, cand[1]):
                    crawl = list_by_title.get(cand)
                    if crawl:
                        break
        url = (crawl or {}).get("url") or rec.get("source_page_url") or ""
        src_type = rec.get("source_type") or (crawl or {}).get("section", "")
        src_type = {"教务通知": "教务处通知"}.get(src_type, src_type)
        art = articles_by_url.get(url) or articles_by_title.get((date, n)) or {}
        body = (art.get("body") or "").strip()
        if not body:
            unmatched.append(f"{date} {title[:30]}")
            # Keep index-only records useful inside the application.  The
            # generated text preserves the key facts (title/date/source) so
            # users and RAG can answer from the PDF even when an article body
            # was not available during crawling.
            body = (f"{title}。发布日期：{date}。来源栏目：{src_type or '校园公开信息'}。"
                    + (f"详情请查看官方链接：{url}" if url else "该记录来自学校公开信息汇总。"))
        content_type = classify(title, body, src_type)
        dept = (art.get("department") or "").strip() or ("教务处" if src_type == "教务处通知" else "")
        out_rows.append({
            "date": date,
            "title": title,
            "body": body,
            "summary": (art.get("summary") or body[:200]),
            "content_type": content_type,
            "tags": derive_tags(title, rec.get("category", ""), src_type, content_type),
            "category": rec.get("category", ""),
            "source_type": "unknown",
            "source_category": src_type,
            "source_url": url,
            "source_page_url": rec.get("source_page_url") or url,
            "source_site": "新疆工程学院",
            "source_department": dept,
            # Stable per-item identity even when several items share a
            # section/list URL (the latter is not an article identifier).
            "source_id": f"{date}|{title}|{url}",
            "publish_time": date,
            "target_colleges": [], "target_majors": [], "target_grades": [],
            "body_source": "fetched_article" if body else "index_only",
        })
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in out_rows) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "total": len(out_rows),
        "sources": dict(Counter(x["source_type"] for x in out_rows)),
        "content_types": dict(Counter(x["content_type"] for x in out_rows)),
        "with_body": sum(bool(x["body"]) for x in out_rows),
        "index_only": sum(not x["body"] for x in out_rows),
        "unmatched_or_no_body": len(unmatched),
    }, ensure_ascii=False))
    if unmatched:
        note = out.with_name("xju_enriched_unmatched.txt")
        note.write_text("\n".join(unmatched), encoding="utf-8")


if __name__ == "__main__":
    main()
