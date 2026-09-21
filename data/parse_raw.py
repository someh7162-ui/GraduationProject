"""Convert a raw text dump of the XJU public-information index into NDJSON records.

Usage (portable, works on Windows and Linux):

    python data/parse_raw.py INPUT.txt OUTPUT.ndjson

INPUT is a text dump whose index section (starting at the marker line
"4. 完整公开信息索引" or "完整公开信息索引") looks like::

    2026-09-09 校园服务/安全
    校党委书记李长江开展新学期校
    园安全走访调研
    https://www.xjie.edu.cn/xyxw1.htm
    校园新闻

Each visual row becomes one JSON line with date/category/title/source fields.
This is a *legacy helper*: the canonical dataset is rebuilt from the live
public website by scripts/fetch_campus_articles.py.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from collections import Counter

sources = {"校园新闻", "通知公告", "教务处通知"}
date_re = re.compile(r"^(20\d\d-\d\d-\d\d)\s+(.+)$")


def parse_index(ls: list[str], start: int) -> list[dict]:
    records: list[dict] = []
    cur: dict | None = None
    pending: list[str] = []
    seen_url = False
    for l in ls[start + 1:]:
        st = l.strip()
        if not st or st.startswith("以下共") or st.startswith("日期") or "新疆工程学院公开校内信息汇总" in st:
            continue
        m = date_re.match(st)
        if m:
            if cur:
                records.append(cur)
            cur = {"date": m.group(1), "category": m.group(2).strip(),
                   "title": " ".join(pending).strip(), "source_type": "",
                   "source_page_url": "", "article_url": "", "summary": ""}
            pending = []
            seen_url = False
            continue
        if cur is None:
            pending.append(st)
            continue
        if st in sources:
            cur["source_type"] = st
            continue
        if st.startswith("http"):
            cur["source_page_url"] += st
            seen_url = True
            continue
        if seen_url:
            # URL continuation lines are path/query fragments.
            if re.match(r"^[A-Za-z0-9_?=&/.\-]+$", st) and ("/" in st or "?" in st or st.endswith(".htm")):
                cur["source_page_url"] += st
                continue
            pending.append(st)
        else:
            cur["title"] += (" " if cur["title"] else "") + st
    if cur:
        records.append(cur)
    return records


def finalize(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        title = re.sub(r"\s+", " ", r["title"]).strip()
        title = re.sub(r"\s*/\s*", "/", title)  # collapse wrapped URLs like "info/\n1058/x.htm"
        if not title:
            continue
        r["title"] = title
        r["source_page_url"] = re.sub(r"\s+", "", r["source_page_url"])
        r["tags"] = [r["category"]] if r["category"] else []
        r["target_grades"] = []
        r["target_majors"] = []
        r["importance"] = 0.5
        r["content_type"] = ("notice" if r["source_type"] == "通知公告"
                             else "academic" if r["source_type"] == "教务处通知" else "news")
        out.append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="path to the raw text dump")
    ap.add_argument("output", help="path to the output .ndjson file")
    args = ap.parse_args()
    text = Path(args.input).read_text(encoding="utf-8")
    ls = text.splitlines()
    marker = next((i for i, l in enumerate(ls) if "完整公开信息索引" in l), None)
    if marker is None:
        sys.exit("error: could not find the '完整公开信息索引' marker in the input")
    records = finalize(parse_index(ls, marker))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    print(json.dumps({
        "records": len(records),
        "sources": dict(Counter(r["source_type"] for r in records)),
        "empty_url": sum(not r["source_page_url"] for r in records),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
