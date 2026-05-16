# -*- coding: utf-8 -*-
"""Parse specialty groups with dates → journals_structured.xlsx."""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from config import AS_OF_LABEL, STRUCTURED_XLSX, pdf_path_for_parsing
from extract_journals import (
    ISSN_RE,
    extract_full_text,
    normalize_issn,
    parse_entry,
    split_entries,
)

DATE_LINE = re.compile(r"^([сС]|по)\s+(\d{2}\.\d{2}\.\d{4})$")
SPEC_START = re.compile(
    r"^("
    r"(?P<vak>\d{1,2}\.\d{1,2}\.\d{1,2})\.\s*"
    r"|(?P<diss>\d{2}\.\d{2}\.\d{2})\s*[–—\-]\s*"
    r")"
)
BRANCH_RE = re.compile(r"\(([^)]+)\)\s*$")
# Split when a new specialty code appears mid-line (after ISSN / rename notes)
EMBEDDED_SPEC = re.compile(
    r"(?=(?:\d{1,2}\.\d{1,2}\.\d{1,2}\.\s)|(?:\d{2}\.\d{2}\.\d{2}\s*[–—\-]\s))"
)
ISSN_INLINE = re.compile(r"[,;\s]*ISSN\s+[\dXxХх\-–—\s,\)»«\"]+", re.IGNORECASE)


@dataclass
class SpecRecord:
    code: str
    code_type: str
    title: str
    branch: str = ""
    date_from: str = ""
    date_to: str = ""
    dates_raw: str = ""
    group_index: int = 0


@dataclass
class JournalSpecs:
    num: int
    name: str
    issn: str
    journal_dates: str
    specs: list[SpecRecord] = field(default_factory=list)
    parse_notes: str = ""


def parse_dates_list(date_strs: list[str]) -> tuple[str, str, str]:
    froms, tos = [], []
    for d in date_strs:
        kind, val = d.split(" ", 1)
        if kind in ("с", "С"):
            froms.append(val)
        elif kind == "по":
            tos.append(val)
    return froms[0] if froms else "", tos[-1] if tos else "", "; ".join(date_strs)


def extract_branch(title: str) -> tuple[str, str]:
    m = BRANCH_RE.search(title)
    if not m:
        return clean_spec_title(title.strip(" ,")), ""
    core = clean_spec_title(title[: m.start()].strip(" ,"))
    return core, m.group(1).strip()


def clean_spec_title(title: str) -> str:
    """Remove ISSN / rename-note debris often injected by PDF line breaks."""
    t = ISSN_INLINE.sub("", title)
    t = re.sub(r"\s+", " ", t).strip(" ,;)")
    return t


def is_issn_junk_line(line: str) -> bool:
    """Lines that are only old ISSN / title fragments, not specialties."""
    if SPEC_START.match(line):
        return False
    if not re.search(r"ISSN", line, re.IGNORECASE):
        return False
    rest = re.sub(r"ISSN\s*", "", line, flags=re.IGNORECASE)
    rest = re.sub(r"[\dXxХх\-–—\s,\)»«\"«]+", "", rest)
    return len(rest) < 2


def expand_spec_lines(lines: list[str]) -> list[str]:
    """One PDF line may contain 'ISSN …) 5.3.4. Title' — split before tokenizing."""
    out: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in EMBEDDED_SPEC.split(line) if p.strip()]
        for part in parts or [line]:
            if not is_issn_junk_line(part):
                out.append(part)
    return out


def tokenize_spec_region(lines: list[str]) -> list[dict]:
    tokens: list[dict] = []
    buf: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        dm = DATE_LINE.match(line)
        if dm:
            if buf:
                tokens.append({"type": "text", "text": " ".join(buf)})
                buf = []
            kind = "с" if dm.group(1) in ("с", "С") else dm.group(1)
            tokens.append({"type": "date", "kind": kind, "value": dm.group(2)})
            continue
        sm = SPEC_START.match(line)
        if sm:
            if buf:
                tokens.append({"type": "text", "text": " ".join(buf)})
                buf = []
            code = sm.group("vak") or sm.group("diss")
            tokens.append(
                {
                    "type": "spec_start",
                    "code": code + ("" if sm.group("diss") else "."),
                    "code_type": "vak" if sm.group("vak") else "diss",
                    "rest": line[sm.end() :].strip(),
                }
            )
            continue
        buf.append(line)
    if buf:
        tokens.append({"type": "text", "text": " ".join(buf)})
    return tokens


def parse_specs_segmented(after_issn: str) -> tuple[list[SpecRecord], str]:
    raw = [l.strip() for l in after_issn.splitlines() if l.strip()]
    lines = expand_spec_lines(raw)
    tokens = tokenize_spec_region(lines)
    segments: list[tuple[list[dict], list[str]]] = []
    current_specs: list[dict] = []
    pending_dates: list[str] = []
    current: dict | None = None
    notes: list[str] = []

    def close_segment():
        nonlocal current_specs, pending_dates
        if current_specs:
            segments.append((current_specs, list(pending_dates)))
        current_specs, pending_dates = [], []

    for tok in tokens:
        if tok["type"] == "date":
            pending_dates.append(f"{tok['kind']} {tok['value']}")
        elif tok["type"] == "spec_start":
            if pending_dates and current_specs:
                close_segment()
            current = {"code": tok["code"], "code_type": tok["code_type"], "title": tok["rest"]}
            current_specs.append(current)
        elif tok["type"] == "text":
            if current is not None:
                current["title"] = (current["title"] + " " + tok["text"]).strip()
            else:
                notes.append(f"orphan_text:{tok['text'][:40]}")
    if pending_dates or current_specs:
        close_segment()

    records: list[SpecRecord] = []
    for gi, (specs, dates) in enumerate(segments):
        d_from, d_to, d_raw = parse_dates_list(dates)
        for s in specs:
            title, branch = extract_branch(s["title"])
            inline = [
                f"{'с' if k in ('с', 'С') else k} {v}"
                for k, v in re.findall(r"\b([сС]|по)\s+(\d{2}\.\d{2}\.\d{4})\b", title)
            ]
            if inline:
                title = re.sub(r"\s*([сС]|по)\s+\d{2}\.\d{2}\.\d{4}\s*", " ", title).strip()
                id_from, id_to, id_raw = parse_dates_list(inline)
                d_from, d_to = d_from or id_from, d_to or id_to
                d_raw = "; ".join(x for x in (d_raw, id_raw) if x)
            records.append(
                SpecRecord(
                    code=s["code"],
                    code_type=s["code_type"],
                    title=title,
                    branch=branch,
                    date_from=d_from,
                    date_to=d_to,
                    dates_raw=d_raw,
                    group_index=gi,
                )
            )
    return records, "; ".join(notes)


def fill_missing_spec_dates(specs: list[SpecRecord], journal_dates: str) -> None:
    j_from, j_to, j_raw = parse_dates_list(
        [d.strip() for d in journal_dates.split(";") if d.strip()]
    )
    last_from, last_to, last_raw = "", "", ""
    for s in specs:
        if s.dates_raw:
            last_from, last_to, last_raw = s.date_from, s.date_to, s.dates_raw
        elif last_from or last_to or last_raw:
            s.date_from, s.date_to, s.dates_raw = last_from, last_to, last_raw
        elif j_from or j_to:
            s.date_from, s.date_to, s.dates_raw = j_from, j_to, j_raw


def find_spec_region_start(block: str) -> int:
    matches = list(ISSN_RE.finditer(block))
    if not matches:
        return 0
    for m in reversed(matches):
        tail = block[m.end() : m.end() + 80]
        if SPEC_START.search(tail.strip()) or re.search(
            r"^\d{1,2}\.\d{1,2}\.\d{1,2}\.", tail.strip()
        ):
            return m.end()
    return matches[-1].end()


def parse_journal(num: int, block: str, journal_row: dict) -> JournalSpecs:
    matches = list(ISSN_RE.finditer(block))
    start = find_spec_region_start(block)
    after = block[start:]
    issn = journal_row["issn"]
    if matches:
        for m in reversed(matches):
            if m.end() <= start + 2:
                issn = normalize_issn(m)
                break
    specs, notes = parse_specs_segmented(after)
    fill_missing_spec_dates(specs, journal_row.get("dates", ""))
    return JournalSpecs(
        num=num,
        name=journal_row["name"],
        issn=issn,
        journal_dates=journal_row.get("dates", ""),
        specs=specs,
        parse_notes=notes,
    )


def parse_all(pdf_path: Path) -> list[JournalSpecs]:
    blocks = dict(split_entries(extract_full_text(pdf_path)))
    return [
        parse_journal(num, blocks[num], parse_entry(num, blocks[num]))
        for num in sorted(blocks)
    ]


def write_xlsx(journals: list[JournalSpecs], out_path: Path) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    catalog: dict[tuple, dict] = {}
    mapping_rows: list[dict] = []
    stats: dict = defaultdict(int)

    for j in journals:
        stats["journals"] += 1
        for s in j.specs:
            stats["links"] += 1
            if s.dates_raw:
                stats["links_with_dates"] += 1
            k = (s.code_type, s.code, s.title, s.branch)
            if k not in catalog:
                catalog[k] = {
                    "spec_id": len(catalog) + 1,
                    "code_type": s.code_type,
                    "code": s.code,
                    "title": s.title,
                    "branch": s.branch,
                    "journal_count": 0,
                }
            catalog[k]["journal_count"] += 1
            mapping_rows.append(
                {
                    "journal_num": j.num,
                    "journal_name": j.name,
                    "issn": j.issn,
                    "spec_id": catalog[k]["spec_id"],
                    "code_type": s.code_type,
                    "code": s.code,
                    "title": s.title,
                    "branch": s.branch,
                    "group_index": s.group_index,
                    "date_from": s.date_from,
                    "date_to": s.date_to,
                    "dates_raw": s.dates_raw,
                    "journal_dates_all": j.journal_dates,
                }
            )

    wb = Workbook()

    def style_header(ws):
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    def autosize(ws, widths):
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws_j = wb.active
    ws_j.title = "Journals"
    ws_j.append(
        ["№", "Наименование", "ISSN", "Даты (журнал)", "Число специальностей", "Примечания"]
    )
    for j in journals:
        ws_j.append([j.num, j.name, j.issn, j.journal_dates, len(j.specs), j.parse_notes])
    style_header(ws_j)
    autosize(ws_j, [6, 42, 14, 28, 10, 20])
    ws_j.freeze_panes = "A2"

    ws_s = wb.create_sheet("Specialties")
    ws_s.append(["spec_id", "code_type", "code", "title", "branch", "journal_count"])
    for row in sorted(catalog.values(), key=lambda x: (x["code_type"], x["code"])):
        ws_s.append(
            [row["spec_id"], row["code_type"], row["code"], row["title"], row["branch"], row["journal_count"]]
        )
    style_header(ws_s)
    autosize(ws_s, [8, 10, 12, 55, 28, 12])

    ws_m = wb.create_sheet("Journal_Spec_Map")
    ws_m.append(
        [
            "journal_num", "journal_name", "issn", "spec_id", "code_type", "code",
            "title", "branch", "group_index", "date_from", "date_to", "dates_raw",
            "journal_dates_all",
        ]
    )
    for r in mapping_rows:
        ws_m.append(list(r.values()))
    style_header(ws_m)
    autosize(ws_m, [8, 42, 14, 8, 10, 12, 45, 25, 8, 12, 12, 28, 28])
    ws_m.freeze_panes = "A2"

    ws_p = wb.create_sheet("Parse_Summary")
    ws_p.append(["metric", "value"])
    for k, v in [
        ("journals", stats["journals"]),
        ("links", stats["links"]),
        ("links_with_dates", stats["links_with_dates"]),
        ("unique_specialties", len(catalog)),
    ]:
        ws_p.append([k, v])
    style_header(ws_p)
    wb.save(out_path)
    return dict(stats) | {"unique_specialties": len(catalog)}


def main() -> int:
    p = argparse.ArgumentParser(description=f"Parse specialties + dates ({AS_OF_LABEL})")
    p.add_argument("--pdf", type=Path, default=None, help="Input PDF (default: SOURCE_URL.txt)")
    p.add_argument("--output", type=Path, default=STRUCTURED_XLSX)
    args = p.parse_args()

    try:
        pdf = args.pdf or pdf_path_for_parsing()
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"Parsing {pdf}…")
    journals = parse_all(pdf)
    links = sum(len(j.specs) for j in journals)
    dated = sum(1 for j in journals for s in j.specs if s.dates_raw)
    print(f"  {len(journals)} journals, {links} links ({dated} with dates)")
    stats = write_xlsx(journals, args.output)
    print(f"Wrote {args.output}")
    print(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
