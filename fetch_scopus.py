# -*- coding: utf-8 -*-
"""Fetch Scopus metadata for all journals with ISSN — concurrent, rate-limited.

Usage:
    python fetch_scopus.py          # fetch missing ISSNs (uses cache)
    python fetch_scopus.py --force  # refetch all ISSNs

Reads ISSNs from docs/data/vak.json, calls Scopus Serial Title API for each,
and saves results to data/scopus_cache.json (ISSN → scopus metadata).

Requires SCOPUS_API_KEY environment variable.
Serial Title API rate limit: 6 requests/second (docs), ~9 min for 3200 ISSNs.
"""
from __future__ import annotations

import json
import os
import sys
import time
import threading
import concurrent.futures
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CACHE_PATH = ROOT / "data" / "scopus_cache.json"
JSON_DATA = ROOT / "docs" / "data" / "vak.json"
SCOPUS_API = "https://api.elsevier.com/content/serial/title/issn/{issn}?apiKey={key}"
MAX_WORKERS = 6       # matches 6 req/s rate limit
RATE_WINDOW = 1.0     # seconds — reset window every 1s
SAVE_INTERVAL = 100   # save cache every N results


def normalize_issn(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(" ", "").upper()
    if len(cleaned) == 8 and cleaned.isdigit():
        return f"{cleaned[:4]}-{cleaned[4:]}"
    if len(cleaned) == 9 and cleaned[4] == "-":
        return cleaned
    return None


def parse_response(raw: dict) -> dict:
    """Parse Scopus API response into a clean metadata dict."""
    root = raw.get("serial-metadata-response")
    if not root:
        return {"inScopus": False}
    entry = root.get("entry", [None])[0]
    if not entry:
        return {"inScopus": False}

    source_id = entry.get("source-id")
    if not source_id:
        return {"inScopus": False}

    result: dict = {"inScopus": True, "sourceId": source_id}

    sjr_list = entry.get("SJRList", {}).get("SJR") or []
    sjr = []
    for s in sjr_list:
        try:
            sjr.append({"year": str(s["@year"]), "value": float(s["$"])})
        except (KeyError, TypeError, ValueError):
            pass
    sjr.sort(key=lambda x: x["year"], reverse=True)
    if sjr:
        result["sjr"] = sjr[:3]

    snip_list = entry.get("SNIPList", {}).get("SNIP") or []
    snip = []
    for s in snip_list:
        try:
            snip.append({"year": str(s["@year"]), "value": float(s["$"])})
        except (KeyError, TypeError, ValueError):
            pass
    snip.sort(key=lambda x: x["year"], reverse=True)
    if snip:
        result["snip"] = snip[:3]

    csi = entry.get("citeScoreYearInfoList", {})
    if csi.get("citeScoreCurrentMetric"):
        result["citeScore"] = float(csi["citeScoreCurrentMetric"])
        result["citeScoreYear"] = str(csi.get("citeScoreCurrentMetricYear", ""))

    for link in (entry.get("link") or []):
        if link.get("@ref") == "scopus-source":
            result["scopusLink"] = link.get("@href")
            break

    return result


def fetch_one(issn: str, api_key: str, rate_lock: threading.Lock,
              rate_ts: list[float]) -> tuple[str, dict | None]:
    """Fetch one ISSN with rate limiting and retry on 429."""
    for attempt in range(4):
        # Rate limit: ensure ≤ MAX_WORKERS requests per RATE_WINDOW
        with rate_lock:
            now = time.monotonic()
            # Remove timestamps outside the window
            rate_ts[:] = [t for t in rate_ts if now - t < RATE_WINDOW]
            if len(rate_ts) >= MAX_WORKERS:
                # Wait until we can send
                sleep_until = rate_ts[0] + RATE_WINDOW
                wait = sleep_until - now
                if wait > 0:
                    time.sleep(wait)
            rate_ts.append(time.monotonic())

        url = SCOPUS_API.format(issn=issn, key=api_key)
        req = Request(url, headers={"Accept": "application/json"})
        try:
            with urlopen(req, timeout=15) as res:
                raw = json.loads(res.read().decode("utf-8"))
            return (issn, parse_response(raw))
        except HTTPError as exc:
            if exc.code == 404:
                return (issn, {"inScopus": False})
            if exc.code == 429:
                wait = 2 ** attempt
                print(f"   429 {issn}, retry in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if exc.code == 401:
                print(f"  ERROR 401: bad API key for {issn}", file=sys.stderr)
                return (issn, None)
            print(f"  HTTP {exc.code} {issn}", file=sys.stderr)
            return (issn, None)
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  Error {issn}: {exc}", file=sys.stderr)
            return (issn, None)

    print(f"   give up {issn} after 4 retries", file=sys.stderr)
    return (issn, None)


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


def fetch_batch(issns: list[str], api_key: str, cache: dict) -> tuple[int, int]:
    """Fetch a batch of ISSNs concurrently with rate limiting."""
    rate_lock = threading.Lock()
    rate_ts: list[float] = []  # timestamps of recent requests
    fetched = 0
    errors = 0
    cache_lock = threading.Lock()

    def worker(issn: str) -> None:
        nonlocal fetched, errors
        _, result = fetch_one(issn, api_key, rate_lock, rate_ts)
        with cache_lock:
            if result is not None:
                cache[issn] = result
                fetched += 1
            else:
                errors += 1
            total = fetched + errors
            if total % SAVE_INTERVAL == 0 or total == len(issns):
                save_cache(cache)
                print(f"   {total}/{len(issns)}  (OK:{fetched}  err:{errors})")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        list(pool.map(worker, issns))
    return fetched, errors


def main() -> int:
    api_key = os.environ.get("SCOPUS_API_KEY", "").strip()
    if not api_key:
        # Fallback: read from .scopus_key file
        key_file = ROOT / ".scopus_key"
        if key_file.is_file():
            api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        print("SCOPUS_API_KEY not set — Scopus data will not be fetched", file=sys.stderr)
        print("To enable: add SCOPUS_API_KEY secret in GitHub repo Settings → Secrets and variables → Actions")
        return 0

    force = "--force" in sys.argv

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

    cache = {} if force else load_cache()
    cached_count = sum(1 for issn in issns if issn in cache)
    to_fetch = [issn for issn in sorted(issns) if issn not in cache]

    print(f"Cached: {cached_count}")
    if force:
        print("Force mode: refetching all ISSNs")
        to_fetch = sorted(issns)
    print(f"To fetch: {len(to_fetch)}")

    if to_fetch:
        # Health check: try one request to detect Elsevier blocking
        test_issn = to_fetch[0]
        test_result = fetch_one(test_issn, api_key, threading.Lock(), [])
        if test_result[1] is None:
            print(f"  Scopus API unreachable (first test failed) — using cached data only")
            save_cache(cache)
        else:
            start = time.time()
            fetched, errors = fetch_batch(to_fetch, api_key, cache)
            elapsed = time.time() - start
            print(f"Fetched: {fetched}, errors: {errors} in {elapsed:.0f}s")
    else:
        print("Nothing to fetch.")
        save_cache(cache)

    merge_scopus(payload, cache, issns)
    print(f"\nMerged into {JSON_DATA}")
    matched = payload["meta"].get("scopus_matched", 0)
    total_no_issn = sum(1 for j in payload["journals"] if not j.get("issn"))
    total_not_found = len(payload["journals"]) - matched - total_no_issn
    print(f"  In Scopus: {matched}")
    print(f"  Not found in Scopus: {total_not_found}")
    print(f"  No ISSN: {total_no_issn}")
    return 0


def merge_scopus(payload: dict, cache: dict, issns: set[str] | None = None) -> int:
    scopus_by_issn: dict[str, dict] = {}
    for issn in cache:
        if issns is None or issn in issns:
            scopus_by_issn[issn] = cache[issn]

    matched = 0
    for j in payload["journals"]:
        normalized = normalize_issn(j.get("issn"))
        if normalized and normalized in scopus_by_issn:
            j["scopus"] = scopus_by_issn[normalized]
            if scopus_by_issn[normalized].get("inScopus"):
                matched += 1
        else:
            j["scopus"] = None

    payload["meta"]["scopus_fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload["meta"]["scopus_matched"] = matched
    return matched


if __name__ == "__main__":
    sys.exit(main())
