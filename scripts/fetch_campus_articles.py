"""Fetch real article bodies for the XJU campus dataset from public pages.

This crawler must be run on a machine that has network access to
www.xjie.edu.cn / jwc.xjie.edu.cn (the sandbox this project was built in has
no outbound network; the bundled data/crawl files were produced with the
harness web tool instead).

It only ever touches public, login-free pages and never requests personal or
login-gated content.  It is idempotent and resumable: rows that already carry
a fetched body are skipped, and rows whose fetch failed keep their previous
content so a re-run only retries the missing ones.

Usage:

    python scripts/fetch_campus_articles.py --input data/xju_enriched.ndjson ^
        --output data/xju_articles.ndjson [--delay 1.0] [--limit 0]

Schema of each written line (superset of the import schema):

    title, date, category, tags, source_type, source_page_url, article_url,
    body, summary, source_site, source_department, content_type,
    publish_time, body_source  ("fetched_article" | "index_only")
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, logging, re, sys, time, zlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger("fetch_campus_articles")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_DATE = re.compile(r"20\d\d[-/]\d{1,2}[-/]\d{1,2}")
_WS = re.compile(r"[ \t\u3000]+")


def norm(s: str) -> str:
    """Whitespace/separator-insensitive normalisation used for title matching."""
    return re.sub(r"[\s…\u3000]+", "", s or "")


class _Text(HTMLParser):
    """Collect visible text; treat p/br/div/headings as line breaks."""

    _BLOCK = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "tr", "td", "section", "article"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.lines: list[str] = []
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag in self._BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag in self._BLOCK:
            self._flush()

    def handle_data(self, data):
        if self._skip == 0:
            self._buf.append(data)

    def _flush(self):
        t = "".join(self._buf).strip()
        self._buf = []
        if t:
            self.lines.append(re.sub(r"[ \t\u3000]+", " ", t))


def visible_text(html: str) -> list[str]:
    p = _Text()
    try:
        p.feed(html)
    except Exception:
        pass
    return p.lines


def find_content_slice(html: str) -> str:
    """Best-effort crop to the article content area of wbx-style CMS pages."""
    for marker in ('class="v_news_content"', "id=\"vsb_content\"",
                   'class="v_news_content"', "vsb_content"):
        i = html.find(marker)
        if i != -1:
            start = html.rfind("<", 0, i)
            return html[start:] if start != -1 else html[i:]
    i = html.find("当前位置")
    if i != -1:
        return html[i:]
    return html


_FOOTER_HITS = ("下一条", "快速通道", "版权所有", "学校地址", "新ICP备",
                "共", "附件【", "电脑版", "手机版", "常用链接")


def extract_article(html: str, title: str = "") -> tuple[str, str]:
    """Return (body, department). Empty body means extraction failed."""
    lines = visible_text(find_content_slice(html))
    # Drop obvious chrome lines and everything after footer markers.
    out: list[str] = []
    for ln in lines:
        if any(ln.startswith(f) or f in ln for f in ("快速通道", "版权所有", "学校地址", "新ICP备")):
            break
        if ln in ("OA系统", "邮件系统") or ln.startswith("下一条") or ln.startswith("上一篇"):
            break
        # skip date/meta line like "发布日期：2026-09-09 来源： 点击量：" on main site
        if re.match(r"^(发布日期|发布时间)", ln) and not out:
            continue
        out.append(ln)
    # The first 1-2 lines often duplicate the <h1>/nav breadcrumb; drop duplicates of title.
    t = norm(title)
    while out and (norm(out[0]) == t or norm(out[0]).startswith(t[:8]) if len(t) >= 8 else False):
        out.pop(0)
    body = "\n".join(out).strip()
    if len(body) < 20:  # almost certainly chrome, not an article
        return "", ""
    dept = ""
    m = re.search(r"来源[:：]\s*([^\s　]+)", lines[0] if lines else "")
    if m:
        dept = m.group(1)
    return body, dept


def http_get(url: str, timeout: int = 15) -> str:
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _find_article_url(list_html: str, want_title: str) -> str:
    """Find the first <a> in a section list page whose text matches want_title."""
    target = norm(want_title)
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', list_html, re.S | re.I):
        href, txt = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if norm(txt) == target or (target and target.startswith(norm(txt)) and len(norm(txt)) >= 12):
            return href
    return ""


def absolutize(base: str, href: str) -> str:
    from urllib.parse import urljoin
    return urljoin(base, href)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0, help="0 = no limit (for tests)")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--resolve", action="store_true",
                    help="discover missing article_url from the record's source list page")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)
    in_path, out_path = Path(args.input), Path(args.output)
    rows = [json.loads(x) for x in in_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    existing: dict[str, dict] = {}
    if out_path.exists():
        for x in out_path.read_text(encoding="utf-8").splitlines():
            if x.strip():
                r = json.loads(x)
                existing[norm(r.get("title", "")) + "|" + str(r.get("date", ""))] = r
    out_rows: list[dict] = []
    fetched = failed = 0
    try:
        for i, row in enumerate(rows):
            key = norm(row.get("title", "")) + "|" + str(row.get("date", ""))
            prev = existing.get(key) or row
            had = str(prev.get("body_source")) == "fetched_article" and (prev.get("body") or "").strip()
            if had:
                out_rows.append(prev)
                continue
            if args.limit and fetched >= args.limit:
                out_rows.append(prev)
                continue
            url = str(prev.get("article_url") or "").strip()
            if not url and args.resolve:
                try:
                    list_url = str(prev.get("source_page_url") or "").strip()
                    if list_url:
                        href = _find_article_url(http_get(list_url, args.timeout), prev.get("title", ""))
                        if href:
                            url = absolutize(list_url, href)
                            prev = dict(prev, article_url=url)
                except Exception as ex:
                    logger.warning("resolve failed %s: %s", prev.get("title", "")[:20], ex)
            if not url:
                logger.warning("no article url, keeping index row: %s", prev.get("title", "")[:30])
                out_rows.append(prev)
                continue
            try:
                html = http_get(url, args.timeout)
                body, dept = extract_article(html, prev.get("title", ""))
                if body:
                    prev = dict(prev, body=body, summary=(prev.get("summary") or body[:200]),
                                source_department=dept or prev.get("source_department") or "",
                                article_url=url, body_source="fetched_article",
                                source_site=prev.get("source_site") or "新疆工程学院",
                                crawl_time=datetime.now(timezone.utc).isoformat())
                    fetched += 1
                else:
                    prev = dict(prev, body_source="index_only")
                    failed += 1
                    logger.warning("empty body: %s", url)
            except (HTTPError, URLError, OSError) as ex:
                failed += 1
                prev = dict(prev, body_source="index_only")
                logger.warning("fetch failed %s: %s", url, ex)
            out_rows.append(prev)
            time.sleep(args.delay)
    finally:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n",
                            encoding="utf-8")
    print(json.dumps({"total": len(rows), "fetched": fetched, "failed": failed},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
