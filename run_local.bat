@echo off
cd /d "%~dp0"
echo == VAK Journals: Local Build ==
echo.

if exist .scopus_key (
    python fetch_scopus.py
    echo.
) else (
    echo [INFO] No .scopus_key file. Scopus data will not be fetched.
    echo.
)
python fetch_rcsi.py
echo.
python build.py --download

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed
    pause
    exit /b 1
)

echo.
echo [DONE] Build complete.
echo.
echo Local preview:
echo   python -m http.server 8080 -d docs
echo.
pause
