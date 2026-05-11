@echo off
title MASTER TERMINAL - sumaryczny widok
cd /d "%~dp0"

REM ====== Auto-detect EA ======
IF EXIST "%USERPROFILE%\Desktop\terminal\signals_unified.db" (
    SET "EA_TERMINAL_ROOT=%USERPROFILE%\Desktop\terminal"
    echo [OK]   EA Terminal: %USERPROFILE%\Desktop\terminal
) ELSE (
    echo [WARN] Brak EA - Master pokaze dane historyczne lub STAND_DOWN
)
echo.

REM ====== Check venv ======
IF NOT EXIST ".venv\Scripts\activate.bat" (
    echo [ERROR] Brak .venv w %CD%
    echo.
    echo Inicjalizacja:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate.bat
    echo   pip install -e .
    echo   pip install pytest pytest-cov
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM ====== 1. Werdykt + audit trail ======
echo ================================================================
echo  CZESC 1/3: WERDYKT MASTERA
echo ================================================================
python -m master.main

echo.
echo ================================================================
echo  CZESC 2/3: 7-LAYER CONFLUENCE BREAKDOWN
echo ================================================================
python scripts\decision.py --since 720

echo.
echo ================================================================
echo  CZESC 3/3: INTERAKTYWNY DASHBOARD HTML
echo ================================================================
python scripts\master_chart.py

echo.
echo ================================================================
echo  Wszystko wygenerowane.
echo  Dashboard otwarty w przegladarce.
echo  HTML zapisany w: output\master_dashboard.html
echo ================================================================
echo.
pause
