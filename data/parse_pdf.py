"""Extract the XJU public-information index from the summary PDF into NDJSON.

Usage (portable, Windows and Linux):

    python data/parse_pdf.py INPUT.pdf OUTPUT.ndjson

The text layer is extracted with pypdf (a declared project dependency); the
layout rows are then parsed by the same engine as parse_layout.py.  Every
visual table row becomes one record.  The per-page lumping behaviour of the
old importer (one record per PDF page) is intentionally *not* reproduced
here: the canonical dataset is rebuilt from the live public website by
scripts/fetch_campus_articles.py and imported record-by-record.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path
from collections import Counter

try:
    from parse_layout import finalize, parse_layout_rows
except ImportError:  # allow `python -m data.parse_pdf` style invocation
    from data.parse_layout import finalize, parse_layout_rows

from pypdf import PdfReader


def extract_text(path: Path) -> list[str]:
    if shutil.which("pdftotext"):
        try:
            proc = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(path), "-"],
                                  check=True, capture_output=True)
            raw = proc.stdout.decode("utf-8", errors="replace")
            return [line for page in raw.split("\f") for line in page.splitlines()]
        except (OSError, subprocess.SubprocessError):
            pass
    lines: list[str] = []
    with PdfReader(str(path)) as reader:
        for page in reader.pages:
            text = page.extract_text() or ""
            lines.extend(text.splitlines())
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="path to the summary PDF")
    ap.add_argument("output", help="path to the output .ndjson file")
    args = ap.parse_args()
    ls = extract_text(Path(args.input))
    marker = next((i for i, l in enumerate(ls) if "完整公开信息索引" in l), None)
    if marker is None:
        sys.exit("error: could not find the '完整公开信息索引' marker in the extracted text")
    records = finalize(parse_layout_rows(ls, marker))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "records": len(records),
        "sources": dict(Counter(r["source_type"] for r in records)),
        "empty_url": sum(not r["source_page_url"] for r in records),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
