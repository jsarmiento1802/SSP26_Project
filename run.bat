@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM COMP-5700 – Security Requirements Change Detector
REM Windows runner script (Task-4 deliverable)
REM
REM Usage:
REM   run.bat <doc1.pdf> <doc2.pdf> [scan_target_dir]
REM
REM Example:
REM   run.bat cis-r1.pdf cis-r2.pdf project-yamls
REM ─────────────────────────────────────────────────────────────────────────

setlocal

if "%~1"=="" goto usage
if "%~2"=="" goto usage

if not exist "%~1" (
    echo Error: PDF not found: %~1
    exit /b 1
)
if not exist "%~2" (
    echo Error: PDF not found: %~2
    exit /b 1
)

cd /d "%~dp0"

if "%~3"=="" (
    python main.py "%~1" "%~2"
) else (
    python main.py "%~1" "%~2" --scan-target "%~3"
)
goto :eof

:usage
echo Usage: %~nx0 ^<doc1.pdf^> ^<doc2.pdf^> [scan_target_dir]
exit /b 1
