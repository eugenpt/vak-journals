# -*- coding: utf-8 -*-
"""Layout-aware reconstruction of the VAK PDF table.

The official PDF is not a tagged table; pypdf exposes positioned text chunks.
This module groups those chunks into visual rows and fixed table columns so
page continuations can be reasoned about as cells instead of text order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path

from pypdf import PdfReader

from extract_journals import HEADER_MARKERS, PAGE_BREAK, SPEC_LINE, is_header_line


DATE_CELL_RE = re.compile(r"^(?:с|по|до)\s+\d{1,2}\.[\d.]{5,}$", re.IGNORECASE)


@dataclass
class LayoutChunk:
    y: float
    x: float
    text: str


@dataclass
class LayoutRow:
    page: int
    y: float
    cells: dict[str, str] = field(default_factory=dict)

    def cell(self, name: str) -> str:
        return self.cells.get(name, "")


@dataclass
class LayoutEntry:
    num: int
    name_lines: list[str] = field(default_factory=list)
    issn_lines: list[str] = field(default_factory=list)
    body_lines: list[str] = field(default_factory=list)
    rows: list[LayoutRow] = field(default_factory=list)


COLUMNS: tuple[tuple[str, float, float], ...] = (
    ("num", 0, 70),
    ("name", 70, 240),
    ("issn", 240, 305),
    ("spec", 305, 505),
    ("date", 505, 700),
)


def column_for_x(x: float) -> str | None:
    for name, left, right in COLUMNS:
        if left <= x < right:
            return name
    return None


def join_text(parts: list[tuple[float, str]]) -> str:
    """Join same-cell chunks while preserving words split into several chunks."""
    out = ""
    prev_x: float | None = None
    for x, raw in sorted(parts):
        text = raw.strip()
        if not text:
            continue
        if not out:
            out = text
        elif text in "-–—" or out.endswith(("-", "–", "—", "(", "«", '"')):
            out += text
        elif prev_x is not None and x - prev_x < 6:
            out += text
        elif text.startswith((",", ".", ")", ":", ";", "»")):
            out += text
        else:
            out += " " + text
        prev_x = x
    return re.sub(r"\s+", " ", out).strip()


def extract_page_chunks(page) -> list[LayoutChunk]:
    chunks: list[LayoutChunk] = []

    def visitor(text, cm, tm, font_dict, font_size):
        s = (text or "").strip()
        if not s or is_header_line(s):
            return
        if any(marker in s for marker in HEADER_MARKERS):
            return
        chunks.append(LayoutChunk(float(tm[5]), float(tm[4]), s))

    page.extract_text(visitor_text=visitor)
    return chunks


def group_rows(chunks: list[LayoutChunk], *, tolerance: float = 3.0) -> list[list[LayoutChunk]]:
    rows: list[list[LayoutChunk]] = []
    for chunk in sorted(chunks, key=lambda c: (-c.y, c.x)):
        for row in rows:
            if abs(row[0].y - chunk.y) <= tolerance:
                row.append(chunk)
                break
        else:
            rows.append([chunk])
    return rows


def extract_page_rows(page, page_no: int) -> list[LayoutRow]:
    rows: list[LayoutRow] = []
    for row_chunks in group_rows(extract_page_chunks(page)):
        cells_parts: dict[str, list[tuple[float, str]]] = {}
        for chunk in row_chunks:
            col = column_for_x(chunk.x)
            if col:
                cells_parts.setdefault(col, []).append((chunk.x, chunk.text))
        cells = {
            name: join_text(parts)
            for name, parts in cells_parts.items()
            if join_text(parts)
        }
        if cells:
            rows.append(LayoutRow(page=page_no, y=max(c.y for c in row_chunks), cells=cells))
    return rows


def rows_to_page_text(rows: list[LayoutRow]) -> str:
    """Serialize visual rows into a line stream compatible with the old parser.

    Dates in the same visual row are emitted before specialty text, reflecting
    the logical date cell rather than pypdf's sometimes column-first text order.
    """
    lines: list[str] = []
    for row in rows:
        prefix = " ".join(
            part for part in (row.cell("num"), row.cell("name"), row.cell("issn")) if part
        ).strip()
        date = row.cell("date")
        spec = row.cell("spec")
        if prefix:
            if date and DATE_CELL_RE.match(date) and spec:
                lines.append(prefix)
                lines.extend(date.splitlines())
                lines.append(spec)
            else:
                lines.append(" ".join(part for part in (prefix, spec, date) if part))
            continue
        if date and DATE_CELL_RE.match(date):
            lines.extend(date.splitlines())
        if spec:
            lines.append(spec)
        elif date and not DATE_CELL_RE.match(date):
            lines.append(date)
        orphan = " ".join(part for part in (row.cell("name"), row.cell("issn")) if part)
        if orphan:
            lines.append(orphan)
    return "\n".join(lines)


def issn_text(text: str) -> str:
    return re.sub(r"\s+", "", text.replace("–", "-").replace("—", "-"))


def append_body_from_row(entry: LayoutEntry, row: LayoutRow, *, page_first_row: bool) -> None:
    date = row.cell("date")
    spec = row.cell("spec")
    if page_first_row and date and DATE_CELL_RE.match(date):
        entry.body_lines.append(date)
        if spec:
            entry.body_lines.append(spec)
        return
    if spec:
        entry.body_lines.append(spec)
    if date:
        entry.body_lines.append(date)


def extract_layout_entries(pdf_path: Path) -> list[LayoutEntry]:
    reader = PdfReader(str(pdf_path))
    entries: list[LayoutEntry] = []
    current: LayoutEntry | None = None

    for page_no, page in enumerate(reader.pages, start=1):
        rows = extract_page_rows(page, page_no)
        for row_i, row in enumerate(rows):
            num_text = row.cell("num")
            num_match = re.match(r"^(\d{1,4})\.", num_text)
            if num_match:
                if current is not None:
                    entries.append(current)
                current = LayoutEntry(num=int(num_match.group(1)))

            if current is None:
                continue

            current.rows.append(row)
            if row.cell("name"):
                current.name_lines.append(row.cell("name"))
            if row.cell("issn"):
                current.issn_lines.append(row.cell("issn"))
            append_body_from_row(current, row, page_first_row=(row_i == 0 and not num_match))

    if current is not None:
        entries.append(current)
    return entries


def layout_entry_to_text(entry: LayoutEntry) -> str:
    name = "\n".join(entry.name_lines)
    issn = issn_text(" ".join(entry.issn_lines))
    head = f"{entry.num}. {name}".strip()
    parts = [head]
    if issn:
        parts.append(issn)
    parts.extend(line for line in entry.body_lines if line)
    return "\n".join(parts)


def extract_layout_entry_text(pdf_path: Path) -> str:
    return "\n".join(layout_entry_to_text(entry) for entry in extract_layout_entries(pdf_path))


def extract_layout_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return PAGE_BREAK.join(
        rows_to_page_text(extract_page_rows(page, page_no))
        for page_no, page in enumerate(reader.pages, start=1)
    )


def debug_rows_for_pages(pdf_path: Path, pages: list[int]) -> None:
    reader = PdfReader(str(pdf_path))
    for page_no in pages:
        print(f"=== PAGE {page_no} ===")
        for row in extract_page_rows(reader.pages[page_no - 1], page_no):
            print(
                f"{row.y:7.1f} | "
                f"N={row.cell('num')!r} | "
                f"NAME={row.cell('name')!r} | "
                f"ISSN={row.cell('issn')!r} | "
                f"SPEC={row.cell('spec')!r} | "
                f"DATE={row.cell('date')!r}"
            )
