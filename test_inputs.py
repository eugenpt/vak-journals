# -*- coding: utf-8 -*-
"""Smoke-test remote URL and local path inputs. Run from repo root with fresh venv."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "SOURCE_URL.txt"
PY = sys.executable
URL = (
    "https://vak.gisnauka.ru/s3-files/01cc80c69fae4988a0246a8f5e2774e7"
    ":fisgna/public/media/uploaded/news_files/2094e02c-d851-48cd-9d57-fe7ebd34a039"
    "/0d03ec3f-666a-44f6-aaad-be1e3051300c.pdf"
)


def run(cmd: list[str], label: str) -> None:
    print(f"\n--- {label} ---")
    print(" ", " ".join(cmd))
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env
    )
    if r.stdout:
        print(r.stdout[-2500:] if len(r.stdout) > 2500 else r.stdout)
    if r.returncode != 0:
        print("STDERR:", r.stderr[-2000:] if r.stderr else "")
        raise SystemExit(r.returncode)


def write_source(value: str) -> None:
    header = """# test run — one line below
# https://vak.gisnauka.ru/documents/editions

"""
    SOURCE.write_text(header + value.strip() + "\n", encoding="utf-8")


def main() -> None:
    backup = SOURCE.read_text(encoding="utf-8") if SOURCE.is_file() else None
    data_pdf = ROOT / "data" / "vak_peer_reviewed_journals.pdf"
    out_dir = ROOT / "output"

    try:
        if data_pdf.is_file():
            data_pdf.unlink()
        if out_dir.is_dir():
            shutil.rmtree(out_dir)

        # 1) Remote URL
        write_source(URL)
        run([PY, "download.py"], "remote: download.py")
        assert data_pdf.is_file(), "remote: cache PDF missing"
        run([PY, "build.py"], "remote: build.py")
        assert (out_dir / "journals.xlsx").is_file()
        assert (out_dir / "journals_structured.xlsx").is_file()
        print("OK remote URL")

        # 2) Local path (copy to temp so we test path, not cache alias)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            local_pdf = Path(tmp.name)
        shutil.copy2(data_pdf, local_pdf)
        if out_dir.is_dir():
            shutil.rmtree(out_dir)

        write_source(str(local_pdf))
        run([PY, "download.py"], "local: download.py")
        run([PY, "extract_journals.py"], "local: extract_journals.py")
        run([PY, "parse_structured.py"], "local: parse_structured.py")
        assert (out_dir / "journals.xlsx").is_file()
        print("OK local path")

        # 3) Relative local path
        rel = Path("data") / "test_local_copy.pdf"
        shutil.copy2(data_pdf, ROOT / rel)
        if out_dir.is_dir():
            shutil.rmtree(out_dir)
        write_source(str(rel))
        run([PY, "build.py"], "relative local: build.py")
        print("OK relative local path")

        local_pdf.unlink(missing_ok=True)
        rel.unlink(missing_ok=True)
        print("\nAll input types passed.")
    finally:
        if backup is not None:
            SOURCE.write_text(backup, encoding="utf-8")


if __name__ == "__main__":
    main()
