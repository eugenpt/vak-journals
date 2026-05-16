# -*- coding: utf-8 -*-
"""Paths and source metadata for the VAK journals list."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE_URL_FILE = ROOT / "SOURCE_URL.txt"
EDITIONS_PAGE = "https://vak.gisnauka.ru/documents/editions"

# As stated in the official PDF title (по состоянию на …)
AS_OF_DATE = "10.04.2026"
AS_OF_LABEL = f"по состоянию на {AS_OF_DATE} г."

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

PDF_PATH = DATA_DIR / "vak_peer_reviewed_journals.pdf"
JOURNALS_XLSX = OUTPUT_DIR / "journals.xlsx"
STRUCTURED_XLSX = OUTPUT_DIR / "journals_structured.xlsx"


def read_source_location() -> str:
    """First non-empty, non-comment line from SOURCE_URL.txt."""
    if not SOURCE_URL_FILE.is_file():
        raise FileNotFoundError(
            f"Missing {SOURCE_URL_FILE.name}. "
            f"Add a PDF URL or local path (see {EDITIONS_PAGE})."
        )
    for line in SOURCE_URL_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise ValueError(
        f"{SOURCE_URL_FILE.name} has no URL or path. "
        f"Paste one line from {EDITIONS_PAGE}"
    )


def is_remote_source(location: str) -> bool:
    return location.startswith(("http://", "https://"))


def resolve_local_path(location: str) -> Path:
    """Resolve a filesystem path (absolute, or relative to repo root)."""
    p = Path(location.strip().strip('"').strip("'")).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    return p


def source_kind(location: str) -> str:
    return "remote" if is_remote_source(location) else "local"


def pdf_path_for_parsing(cache: Path | None = None) -> Path:
    """
    Path to the PDF used by extract/parse scripts.
    - Local line in SOURCE_URL.txt → that file (must exist).
    - URL → cached file under data/ (run download.py first).
    """
    cache = cache or PDF_PATH
    location = read_source_location()
    if source_kind(location) == "local":
        path = resolve_local_path(location)
        if not path.is_file():
            raise FileNotFoundError(f"Local PDF not found: {path}")
        return path
    if cache.is_file():
        return cache
    raise FileNotFoundError(
        f"PDF not downloaded yet. URL in {SOURCE_URL_FILE.name}\n"
        f"Run: python download.py"
    )
