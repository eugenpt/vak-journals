# -*- coding: utf-8 -*-
"""
Fetch the VAK journals list PDF.

SOURCE_URL.txt must contain one line: HTTPS URL or local file path.
Find the current PDF at https://vak.gisnauka.ru/documents/editions
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

from config import (
    AS_OF_LABEL,
    EDITIONS_PAGE,
    PDF_PATH,
    is_remote_source,
    read_source_location,
    resolve_local_path,
    source_kind,
)


def fetch_pdf(
    dest: Path | None = None,
    location: str | None = None,
    force: bool = False,
) -> Path:
    dest = dest or PDF_PATH
    location = location or read_source_location()
    dest.parent.mkdir(parents=True, exist_ok=True)

    if source_kind(location) == "local":
        src = resolve_local_path(location)
        if not src.is_file():
            raise FileNotFoundError(f"Local PDF not found: {src}")
        if dest.resolve() == src.resolve():
            print(f"Using local PDF ({AS_OF_LABEL}): {src}")
            return src
        if dest.is_file() and not force:
            print(f"Cache already exists: {dest}")
            print(f"  Source: {src}")
            print("  Use --force to copy again from local path")
            return dest
        print(f"Copying local PDF ({AS_OF_LABEL})")
        print(f"  from: {src}")
        print(f"  to:   {dest}")
        shutil.copy2(src, dest)
        return dest

    if dest.is_file() and not force:
        print(f"PDF already exists: {dest}")
        print(f"  ({AS_OF_LABEL} — use --force to re-download)")
        return dest

    if not is_remote_source(location):
        raise ValueError(f"Unsupported source (expected http(s) URL or file path): {location}")

    print(f"Downloading ({AS_OF_LABEL})")
    print(f"  {location}")
    req = urllib.request.Request(
        location,
        headers={"User-Agent": "vak-journals-scripts/0.1"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()[:16]
    print(f"Saved {dest} ({len(data):,} bytes, sha256:{digest}…)")
    return dest


def main() -> None:
    p = argparse.ArgumentParser(
        description=f"Get VAK list PDF ({AS_OF_LABEL})",
        epilog=f"Set URL or local path in SOURCE_URL.txt (see {EDITIONS_PAGE})",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--force", action="store_true", help="Re-download or re-copy")
    p.add_argument(
        "--source",
        help="Override SOURCE_URL.txt (https://… or path to a local .pdf)",
    )
    p.add_argument(
        "--output",
        type=Path,
        help="Cache path for remote downloads (default: data/vak_peer_reviewed_journals.pdf)",
    )
    args = p.parse_args()
    fetch_pdf(dest=args.output, location=args.source, force=args.force)


if __name__ == "__main__":
    main()
