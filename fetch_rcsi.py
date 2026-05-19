# -*- coding: utf-8 -*-
"""Fetch RCSI (Белый список РЦНИ) metadata for all journals with ISSN.

Usage:
    python fetch_rcsi.py          # fetch missing ISSNs (uses cache)
    python fetch_rcsi.py --force  # refetch all ISSNs

Reads ISSNs from docs/data/vak.json, calls RCSI API for each,
and saves results to data/rcsi_cache.json (ISSN → rcsi metadata).

API: https://journalrank.rcsi.science/api/record-sources/{issn}/level
No auth required, no rate limiting observed.
"""
from __future__ import annotations

import json
import os
import sys
import time
import concurrent.futures
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "rcsi_cache.json"
JSON_DATA = ROOT / "docs" / "data" / "vak.json"
RCSI_API = "https://journalrank.rcsi.science/api/record-sources/{issn}/level"
MAX_WORKERS = 20
SAVE_INTERVAL = 200


def normalize_issn(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(" ", "").upper()
    if len(cleaned) == 8 and cleaned.isdigit():
        return cleaned
    if len(cleaned) == 9 and cleaned[4] == "-":
        return cleaned.replace("-", "")
    return None


def fetch_one(issn: str) -> tuple[str, dict | None]:
    """Fetch RCSI metadata for one ISSN (no dashes)."""
    url = RCSI_API.format(issn=issn)
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=15) as res:
            raw = json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            return (issn, {"inRcsi": False})
        return (issn, None)
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return (issn, None)

    if raw.get("status") == 404:
        return (issn, {"inRcsi": False})

    result: dict = {"inRcsi": True}
    for field in ("id", "level_2023", "level_2025", "dateAccepted", "dateDiscontinued"):
        if raw.get(field) is not None:
            result[field] = raw[field]

    if raw.get("url"):
        result["url"] = raw["url"]

    return (issn, result)


def load_cache() -> dict:
    if CACHE_PATH.is_file():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> int:
    if not JSON_DATA.is_file():
        print(f"ERROR: {JSON_DATA} not found. Run build.py first.", file=sys.stderr)
        return 1

    payload = json.loads(JSON_DATA.read_text(encoding="utf-8"))
    journals = payload["journals"]

    issns: set[str] = set()
    for j in journals:
        normalized = normalize_issn(j.get("issn"))
        if normalized:
            issns.add(normalized)

    print(f"Journals with ISSN: {len(issns)}")

    force = "--force" in sys.argv
    cache = {} if force else load_cache()
    cached_count = sum(1 for issn in issns if issn in cache)
    to_fetch = [issn for issn in sorted(issns) if issn not in cache]

    print(f"Cached: {cached_count}")
    if force:
        print("Force mode: refetching all ISSNs")
        to_fetch = sorted(issns)
    print(f"To fetch: {len(to_fetch)}")

    if to_fetch:
        fetched = 0
        errors = 0
        start = time.time()

        def worker(issn: str) -> None:
            nonlocal fetched, errors
            _, result = fetch_one(issn)
            if result is not None:
                cache[issn] = result
                fetched += 1
            else:
                errors += 1
            if (fetched + errors) % SAVE_INTERVAL == 0 or (fetched + errors) == len(to_fetch):
                save_cache(cache)
                print(f"  {fetched + errors}/{len(to_fetch)}  (OK:{fetched}  err:{errors})")

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            list(pool.map(worker, to_fetch))

        elapsed = time.time() - start
        print(f"Fetched: {fetched}, errors: {errors} in {elapsed:.0f}s")
    else:
        print("Nothing to fetch.")
        save_cache(cache)

    merge(payload, cache, issns)
    print(f"\nMerged into {JSON_DATA}")
    matched = payload["meta"].get("rcsi_matched", 0)
    total_no_issn = sum(1 for j in payload["journals"] if not j.get("issn"))
    total_not_found = len(payload["journals"]) - matched - total_no_issn
    print(f"  In RCSI: {matched}")
    print(f"  Not found in RCSI: {total_not_found}")
    print(f"  No ISSN: {total_no_issn}")
    return 0


def merge(payload: dict, cache: dict, issns: set[str] | None = None) -> int:
    """Merge RCSI cache data into the payload journals array (in-place).

    Returns number of journals matched (in RCSI).
    """
    rcsi_by_issn: dict[str, dict] = {}
    for issn in cache:
        if issns is None or issn in issns:
            rcsi_by_issn[issn] = cache[issn]

    matched = 0
    for j in payload["journals"]:
        normalized = normalize_issn(j.get("issn"))
        if normalized and normalized in rcsi_by_issn:
            j["rcsi"] = rcsi_by_issn[normalized]
            if rcsi_by_issn[normalized].get("inRcsi"):
                matched += 1
        else:
            j["rcsi"] = None

    payload["meta"]["rcsi_fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload["meta"]["rcsi_matched"] = matched
    return matched


if __name__ == "__main__":
    sys.exit(main())
