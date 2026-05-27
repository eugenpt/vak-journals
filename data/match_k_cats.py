"""Match K1/K2/K3 categories from the VAK distribution PDF into vak.json."""
import json, re
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent.parent
TXT = HERE / "data" / "vak_k_categories.txt"
PDF = HERE / "data" / "vak_k_categories.pdf"
JSON = HERE / "docs" / "data" / "vak.json"

# Cyrillic helpers
_NO = chr(0x2116)  # №
_IT = chr(0x0418) + chr(0x0442) + chr(0x043E) + chr(0x0433) + chr(0x043E) + chr(0x0432) + chr(0x0430) + chr(0x044F)
_RA = (chr(0x0420) + chr(0x0430) + chr(0x0441) + chr(0x043F) + chr(0x0440) + chr(0x0435) + chr(0x0434) +
       chr(0x0435) + chr(0x043B) + chr(0x0435) + chr(0x043D) + chr(0x0438) + chr(0x0435))
_CYR_K = chr(0x041A)
_CYR_DO = chr(0x0434) + chr(0x043E)  # до

# Quote/dash chars
_al = chr(0x00AB)
_ar = chr(0x00BB)
_cl = chr(0x201C)
_cr = chr(0x201D)
_d1 = chr(0x2013)
_d2 = chr(0x2014)
_d3 = chr(0x2015)
RE_ANGLE = re.compile(f"{_al}[^{_ar}]*{_ar}")
RE_CURLY = re.compile(f"{_cl}[^{_cr}]*{_cr}")
RE_DASHES = re.compile(f"[{_d1}{_d2}{_d3}]")
RE_ALLQ = re.compile(f"[,;.:/&\\\\\"{_al}{_ar}{_cl}{_cr}{chr(0x2018)}{chr(0x2019)}'`]")
# Remove parenthesized content — handle unclosed parens too
RE_PARENS = re.compile(r"\([^()]*(?:\)|$)")


def strip_parens(s: str) -> str:
    """Remove all parenthesized text (handles unclosed parens)."""
    while "(" in s:
        s = RE_PARENS.sub("", s)
    return s


def parse_k_cats(txt_path: Path, pdf_path: Path) -> dict[str, str]:
    """Parse K-category data. Reads from .txt if exists, otherwise extracts from PDF."""
    lines: list[str]
    if txt_path.is_file():
        lines = txt_path.read_text(encoding="utf-8").splitlines()
    elif pdf_path.is_file():
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        lines = []
        for page in reader.pages:
            for l in (page.extract_text() or "").splitlines():
                l = l.strip()
                if l:
                    lines.append(l)
    else:
        print("No K-category data source found. Skipping.", file=__import__("sys").stderr)
        return {}

    entries = {}
    skip_prefixes = (_NO, _IT, _RA)
    for line in lines:
        line = line.strip()
        if not line or line.startswith(skip_prefixes):
            continue
        m = re.search(rf"\b({_CYR_K}[123])\s+(\d{{2}}\.\d{{2}}\.\d{{4}})$", line)
        if m:
            rest = line[: m.start()].strip()
            nm = re.match(r"(\d+)\s+(.*)", rest)
            if nm:
                entries[nm.group(2).strip()] = m.group(1)
    return entries


def norm(s: str) -> str:
    n = s.lower().strip()
    n = strip_parens(n)
    n = RE_ANGLE.sub(" ", n)
    n = RE_CURLY.sub(" ", n)
    n = re.sub(r"\bissn\s*[\dx\-]+", "", n)
    n = re.sub(
        rf"\b({chr(0x0441)}|{chr(0x043F)+chr(0x043E)}|{_CYR_DO}|{chr(0x043E)+chr(0x0442)})\s*\d{{1,2}}\.\d{{1,2}}\.\d{{2,4}}\b",
        "", n,
    )
    n = RE_ALLQ.sub(" ", n)
    n = RE_DASHES.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def prepare_main(name: str) -> str:
    n = name
    n = strip_parens(n)
    n = RE_ANGLE.sub(" ", n)
    n = RE_CURLY.sub(" ", n)
    n = re.sub(r"\bissn\s*[\dx\-]+.*$", "", n, flags=re.IGNORECASE)
    n = re.sub(rf"\b{_CYR_DO}\s+\d{{2}}\.\d{{2}}\.\d{{4}}", "", n)
    return n.strip()


def main():
    print("Reading K-categories...", end=" ", flush=True)
    entries = parse_k_cats(TXT, PDF)
    lookup = {norm(k): v for k, v in entries.items()}
    print(f"{len(entries)} entries, {len(lookup)} keys")

    d = json.loads(JSON.read_text(encoding="utf-8"))

    matched = 0
    unmatched = []
    for j in d["journals"]:
        prepped = prepare_main(j["name"])
        key = norm(prepped)
        cat = lookup.get(key)
        if not cat:
            for sep in (" /", f" {_d1}", f" {_d2}", " -"):
                cat = lookup.get(key.split(sep)[0].strip())
                if cat:
                    break
        j["vak_cat"] = cat
        if cat:
            matched += 1
        else:
            unmatched.append(j["name"])

    print(f"Matched: {matched}/{len(d['journals'])} ({matched/len(d['journals'])*100:.1f}%)")
    print(f"Unmatched: {len(unmatched)}")
    dist = Counter(j.get("vak_cat") for j in d["journals"])
    print(f"Distribution: {dict(dist)}")

    if unmatched:
        print("\nUnmatched:")
        for name in unmatched[:20]:
            print(f"  - {name[:90]}")

    JSON.write_text(
        json.dumps(d, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"\nSaved to {JSON}")


if __name__ == "__main__":
    main()
