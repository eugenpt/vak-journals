# -*- coding: utf-8 -*-
"""Export parsed data to JSON for the GitHub Pages frontend."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import AS_OF_DATE, AS_OF_LABEL, EDITIONS_PAGE, ROOT
from parse_structured import JournalSpecs, parse_all

DOCS_DATA = ROOT / "docs" / "data" / "vak.json"


def ru_to_iso(d: str) -> str | None:
    """DD.MM.YYYY -> YYYY-MM-DD for clients."""
    if not d or not d.strip():
        return None
    parts = d.strip().split(".")
    if len(parts) != 3:
        return None
    day, month, year = parts
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def build_payload(journals: list[JournalSpecs]) -> dict:
    catalog: dict[tuple, int] = {}
    specialties: list[dict] = []
    links: list[dict] = []

    for j in journals:
        for s in j.specs:
            k = (s.code_type, s.code, s.title, s.branch)
            if k not in catalog:
                sid = len(specialties) + 1
                catalog[k] = sid
                search = " ".join(
                    x for x in (s.code, s.title, s.branch) if x
                ).lower()
                specialties.append(
                    {
                        "id": sid,
                        "code": s.code,
                        "type": s.code_type,
                        "title": s.title,
                        "branch": s.branch or None,
                        "search": search,
                    }
                )
            link = {
                "j": j.num,
                "s": catalog[k],
                "from": s.date_from or None,
                "to": s.date_to or None,
                "from_iso": ru_to_iso(s.date_from),
                "to_iso": ru_to_iso(s.date_to),
                "g": s.group_index,
            }
            if s.date_from_unreliable:
                link["from_unreliable"] = True
            if s.date_to_unreliable:
                link["to_unreliable"] = True
            if s.date_notes:
                link["date_notes"] = s.date_notes
            links.append(link)

    journal_rows = []
    for j in journals:
        search = " ".join(x for x in (j.name, j.issn) if x).lower()
        journal_rows.append(
            {
                "n": j.num,
                "name": j.name,
                "issn": j.issn or None,
                "dates": j.journal_dates or None,
                "search": search,
            }
        )

    return {
        "meta": {
            "as_of": AS_OF_DATE,
            "as_of_label": AS_OF_LABEL,
            "editions_url": EDITIONS_PAGE,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "journal_count": len(journal_rows),
            "specialty_count": len(specialties),
            "link_count": len(links),
        },
        "journals": journal_rows,
        "specialties": specialties,
        "links": links,
    }


def write_json(journals: list[JournalSpecs], out_path: Path | None = None) -> Path:
    out_path = out_path or DOCS_DATA
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload(journals)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    from config import pdf_path_for_parsing

    pdf = pdf_path_for_parsing()
    print(f"Parsing {pdf}…")
    journals = parse_all(pdf)
    path = write_json(journals)
    size = path.stat().st_size
    print(f"Wrote {path} ({size:,} bytes)")


if __name__ == "__main__":
    main()
