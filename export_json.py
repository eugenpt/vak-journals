# -*- coding: utf-8 -*-
"""Export parsed data to JSON for the GitHub Pages frontend."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape as xml_escape

from config import (
    AS_OF_DATE,
    AS_OF_LABEL,
    EDITIONS_PAGE,
    PASSPORT_NEWS_API,
    ROOT,
    SITE_URL,
    SITEMAP_XML,
    SCOPUS_CACHE,
    RCSI_CACHE,
)
from parse_structured import JournalSpecs, parse_all

DOCS_DATA = ROOT / "docs" / "data" / "vak.json"
PASSPORT_LINK_RE = re.compile(r"^\s*(\d+(?:\.\d+)+\.?)\s*(.+?)\s*$")


def ru_to_iso(d: str) -> str | None:
    """DD.MM.YYYY -> YYYY-MM-DD for clients."""
    if not d or not d.strip():
        return None
    parts = d.strip().split(".")
    if len(parts) != 3:
        return None
    day, month, year = parts
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def normalize_spec_code(code: str) -> str:
    return re.sub(r"\s+", "", code or "").rstrip(".")


def node_text(node: object) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return "".join(node_text(child) for child in node.get("children", []))
    if isinstance(node, list):
        return "".join(node_text(child) for child in node)
    return ""


def extract_passport_links(info: object) -> list[dict]:
    links: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, dict):
            return

        attrs = node.get("attributes", {})
        href = attrs.get("href") if isinstance(attrs, dict) else None
        if node.get("type") == "a" and href:
            label = re.sub(r"\s+", " ", node_text(node)).strip()
            match = PASSPORT_LINK_RE.match(label)
            if match:
                code, title = match.groups()
                links.append(
                    {
                        "code": code,
                        "title": title.strip(),
                        "url": href,
                    }
                )
        for child in node.get("children", []):
            walk(child)

    if isinstance(info, str):
        info = json.loads(info)
    walk(info)

    deduped = []
    seen = set()
    for link in links:
        key = (normalize_spec_code(link["code"]), link["title"], link["url"])
        if key not in seen:
            seen.add(key)
            deduped.append(link)
    return deduped


def fetch_passport_links(timeout: int = 20) -> list[dict]:
    req = Request(
        PASSPORT_NEWS_API,
        headers={
            "Accept": "application/json",
            "User-Agent": "vak-journals/1.0 (+https://eugenpt.github.io/vak-journals/)",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Warning: passport index unavailable: {exc}")
        return []

    results = payload.get("results", [])
    item = next(
        (
            row
            for row in results
            if "паспорт" in str(row.get("name", "")).casefold()
            and "специаль" in str(row.get("name", "")).casefold()
        ),
        None,
    )
    if not item:
        return []
    try:
        return extract_passport_links(item.get("info") or [])
    except (TypeError, json.JSONDecodeError) as exc:
        print(f"Warning: cannot parse passport index: {exc}")
        return []


def apply_passports(payload: dict, passports: list[dict]) -> int:
    by_code: dict[str, dict] = {}
    for passport in passports:
        code = normalize_spec_code(passport["code"])
        by_code.setdefault(code, passport)

    matched = 0
    for specialty in payload["specialties"]:
        passport = by_code.get(normalize_spec_code(specialty["code"]))
        if not passport:
            continue
        specialty["passport"] = {
            "title": passport["title"],
            "url": passport["url"],
        }
        matched += 1
    payload["meta"]["passport_source_url"] = PASSPORT_NEWS_API
    payload["meta"]["passport_count"] = len(passports)
    payload["meta"]["passport_match_count"] = matched
    return matched


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


def apply_scopus(payload: dict) -> int:
    """Merge Scopus cache data into payload journals (in-place).

    Returns number of journals in Scopus, or 0 if no cache or no key.
    """
    if not SCOPUS_CACHE.is_file():
        return 0

    try:
        from fetch_scopus import merge_scopus, normalize_issn
    except ImportError:
        return 0

    cache = json.loads(SCOPUS_CACHE.read_text(encoding="utf-8"))
    if not cache:
        return 0

    # Collect relevant ISSNs from payload
    issns: set[str] = set()
    for j in payload["journals"]:
        normalized = normalize_issn(j.get("issn"))
        if normalized:
            issns.add(normalized)

    return merge_scopus(payload, cache, issns)


def apply_rcsi(payload: dict) -> int:
    """Merge RCSI cache data into payload journals (in-place).

    Returns number of journals in RCSI, or 0 if no cache.
    """
    if not RCSI_CACHE.is_file():
        return 0

    try:
        from fetch_rcsi import merge, normalize_issn
    except ImportError:
        return 0

    cache = json.loads(RCSI_CACHE.read_text(encoding="utf-8"))
    if not cache:
        return 0

    issns: set[str] = set()
    for j in payload["journals"]:
        normalized = normalize_issn(j.get("issn"))
        if normalized:
            issns.add(normalized)

    return merge(payload, cache, issns)


def build_sitemap() -> str:
    urls = [SITE_URL]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        lines.extend(
            [
                "  <url>",
                f"    <loc>{xml_escape(url)}</loc>",
                "    <changefreq>monthly</changefreq>",
                "  </url>",
            ]
        )
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def write_json(journals: list[JournalSpecs], out_path: Path | None = None) -> Path:
    out_path = out_path or DOCS_DATA
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload(journals)
    passport_matches = apply_passports(payload, fetch_passport_links())
    print(
        "Passport links: "
        f"{payload['meta'].get('passport_count', 0)} found, "
        f"{passport_matches} matched"
    )
    scopus_matched = apply_scopus(payload)
    if scopus_matched:
        print(
            "Scopus: "
            f"{scopus_matched} journals in Scopus"
        )
    rcsi_matched = apply_rcsi(payload)
    if rcsi_matched:
        print(
            "RCSI: "
            f"{rcsi_matched} journals in RCSI"
        )
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    SITEMAP_XML.write_text(build_sitemap(), encoding="utf-8")
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
