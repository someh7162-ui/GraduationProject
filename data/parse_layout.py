"""Convert a layout-preserving text dump of the XJU index into NDJSON records.

Usage (portable, Windows and Linux):

    python data/parse_layout.py INPUT.txt OUTPUT.ndjson

INPUT comes from a PDF page-layout text extraction whose index section rows
spread over several lines, for example::

    校党委书记李长江开展新学期校
    2026-09-09    校园服务/安全        园安全走访调研
                                  校园新闻
                                  https://www.xjie.edu.cn/xyxw1.htm

Rows are detected by a leading date field (YYYY-MM-DD possibly after
whitespace); wrapped title fragments are accumulated until the next row.
This is a *legacy helper*: the canonical dataset is rebuilt from the live
public website by scripts/fetch_campus_articles.py.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from collections import Counter

sources = {"校园新闻", "通知公告", "教务处通知"}
date_re = re.compile(r"^\s*(20\d\d-\d\d-\d\d)")


def parse_layout_rows(ls: list[str], start: int) -> list[dict]:
    records: list[dict] = []
    cur: dict | None = None
    pending: list[str] = []
    seen_url = False
    for raw in ls[start + 1:]:
        st = raw.strip()
        if not st or "新疆工程学院公开校内信息汇总" in raw or st.startswith("日期") or st.startswith("以下共"):
            continue
        m = date_re.match(raw)
        if m:
            if cur:
                records.append(cur)
            parts = re.split(r"\s{2,}", st)
            cat = parts[1] if len(parts) > 1 else ""
            src = next((x for x in parts[1:] if x in sources), "")
            inline = next((x for x in parts[2:] if x and x not in sources), "")
            inline_url = inline if inline.startswith("http") else ""
            inline_title = "" if inline_url else inline
            title = " ".join([*pending, inline_title]).strip()
            pending = []
            cur = {"date": m.group(1), "category": cat, "title": title,
                   "source_type": src, "source_page_url": inline_url, "article_url": "",
                   "summary": ""}
            seen_url = bool(inline_url)
            continue
        if cur is None:
            if st.startswith("http") or st in sources:
                continue
            pending.append(st)
            continue
        if st.startswith("http"):
            cur["source_page_url"] += st
            seen_url = True
            continue
        # ``\w`` also matches Chinese in Python; restrict URL continuations to
        # ASCII so wrapped Chinese titles are not swallowed into the URL.
        if seen_url and re.match(r"^[A-Za-z0-9_?=&/.\-]+$", st) and not any(c in st for c in "，。；："):
            cur["source_page_url"] += st
            continue
        if st in sources:
            cur["source_type"] = st
            continue
        if not seen_url:
            cur["title"] += (" " if cur["title"] else "") + st
        else:
            pending.append(st)
    if cur:
        records.append(cur)
    return records


def finalize(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        r["title"] = re.sub(r"\s+", " ", r["title"]).strip()
        r["source_page_url"] = re.sub(r"\s+", "", r["source_page_url"])
        if not r["title"]:
            continue
        r["tags"] = [r["category"]] if r["category"] else []
        r["target_grades"] = []
        r["target_majors"] = []
        r["importance"] = 0.5
        r["content_type"] = ("notice" if r["source_type"] == "通知公告"
                             else "academic" if r["source_type"] in ("教务处通知", "教务通知") else "news")
        out.append(r)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="path to the layout text dump")
    ap.add_argument("output", help="path to the output .ndjson file")
    args = ap.parse_args()
    ls = Path(args.input).read_text(encoding="utf-8").splitlines()
    marker = next((i for i, l in enumerate(ls) if "完整公开信息索引" in l), None)
    if marker is None:
        sys.exit("error: could not find the '完整公开信息索引' marker in the input")
    records = finalize(parse_layout_rows(ls, marker))
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
