# -*- coding: utf-8 -*-
"""Run the full pipeline: download PDF → both XLSX files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import AS_OF_LABEL, JOURNALS_XLSX, PDF_PATH, SITEMAP_XML, STRUCTURED_XLSX, pdf_path_for_parsing, source_kind
from config import read_source_location
from download import fetch_pdf
from config import JSON_DATA
from export_json import write_json
from extract_journals import parse_all as extract_all, write_xlsx as write_journals
from parse_structured import parse_all as parse_structured_all, write_xlsx as write_structured


def build(
    pdf: Path | None = None,
    *,
    download: bool = False,
    force_download: bool = False,
) -> dict:
    if pdf is None:
        loc = read_source_location()
        if source_kind(loc) == "remote" and (download or force_download or not PDF_PATH.is_file()):
            fetch_pdf(force=force_download)
        pdf = pdf_path_for_parsing()
    elif not pdf.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf}")

    print(f"\n=== extract_journals ({AS_OF_LABEL}) ===")
    rows = extract_all(pdf)
    print(f"  {len(rows)} journals")
    write_journals(rows, JOURNALS_XLSX)
    print(f"  -> {JOURNALS_XLSX}")

    print(f"\n=== parse_structured ===")
    journals = parse_structured_all(pdf)
    stats = write_structured(journals, STRUCTURED_XLSX)
    print(f"  -> {STRUCTURED_XLSX}")

    print(f"\n=== export_json (docs) ===")
    json_path = write_json(journals, JSON_DATA)
    print(f"  -> {json_path} ({json_path.stat().st_size:,} bytes)")
    print(f"  -> {SITEMAP_XML} ({SITEMAP_XML.stat().st_size:,} bytes)")

    return {"pdf": str(pdf), "journals": len(rows), "json": str(json_path), **stats}


def main() -> int:
    p = argparse.ArgumentParser(description=f"Build VAK tables ({AS_OF_LABEL})")
    p.add_argument("--download", "-d", action="store_true", help="Download PDF if missing")
    p.add_argument("--force-download", action="store_true", help="Re-download PDF first")
    p.add_argument(
        "--pdf",
        type=Path,
        help="PDF path (default: from SOURCE_URL.txt, or data/ cache after download)",
    )
    args = p.parse_args()

    result = build(
        pdf=args.pdf,
        download=args.download,
        force_download=args.force_download,
    )
    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
