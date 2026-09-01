:: ===========================================================================
:: Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
:: 
:: Author: NuSummit Developers
::
:: ===========================================================================

@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  AMC Context-Engineering -- Portable Launcher
::  run_project.bat
::
::  Steps:
::    1. Validate Python 3.10+
::    2. Create .venv if absent (in streamlit_app\)
::    3. Install / sync all requirements (streamlit_app + backend)
::    4. Verify key imports (neo4j, streamlit, fastapi, uvicorn)
::    5. Auto-find Neo4j and start it
::    6. Wait for Neo4j Bolt (port 7687) to accept connections
::    7. Verify Neo4j driver can connect
::    8. Start FastAPI backend (port 8000)
::    9. Start Streamlit app (port 8501)
::   10. Open browser & print all access URLs
::   11. Graceful shutdown on keypress
:: ============================================================

:: ── Project root is where this .bat lives ────────────────────────────────
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "STREAMLIT_DIR=%ROOT%\streamlit_app"
set "BACKEND_DIR=%ROOT%\backend"
set "VENV_DIR=%STREAMLIT_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "VENV_STREAMLIT=%VENV_DIR%\Scripts\streamlit.exe"

set "NEO4J_BOLT_PORT=7687"
set "NEO4J_HTTP_PORT=7474"
set "API_PORT=8000"
set "STREAMLIT_PORT=8501"

set "LOG_DIR=%ROOT%\logs"
set "NEO4J_LOG=%LOG_DIR%\neo4j.log"
set "API_LOG=%LOG_DIR%\api.log"
set "STREAMLIT_LOG=%LOG_DIR%\streamlit.log"

:: ── Make log directory ───────────────────────────────────────────────────
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo ============================================================
echo   AMC Context-Engineering -- Portable Launcher
echo ============================================================
echo.

:: ────────────────────────────────────────────────────────────────────────
::  Guard: project structure check
:: ────────────────────────────────────────────────────────────────────────
if not exist "%STREAMLIT_DIR%\app.py" (
    echo [FAIL] Cannot find: %STREAMLIT_DIR%\app.py
    echo.
    echo  ERROR: This batch file must sit in the project ROOT folder.
    echo  Expected layout:
    echo    context-engineering\
    echo      run_project.bat   ^<-- this file
    echo      streamlit_app\app.py
    echo      backend\app\main.py
    echo.
    REM pause & exit /b 1
)
if not exist "%BACKEND_DIR%\app\main.py" (
    echo [FAIL] Cannot find: %BACKEND_DIR%\app\main.py
    echo.
    echo  ERROR: backend folder appears incomplete or missing.
    pause & exit /b 1
)

:: ============================================================
::  STEP 1 -- Validate Python 3.10+
:: ============================================================
echo [STEP 1/9] Checking Python...
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python not found on PATH.
    echo.
    echo  ERROR: Python 3.10 or later is required but was not found.
    echo.
    echo  How to fix:
    echo    1. Download Python 3.10+ from https://www.python.org/downloads/
    echo    2. During install, CHECK "Add Python to PATH"
    echo    3. Close this window, open a new terminal, re-run this bat
    echo.
    pause & exit /b 1
)

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :python_too_old

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
goto :python_ok

:python_too_old
echo [FAIL] Python !PY_VER! detected -- need 3.10+
echo.
echo  ERROR: This project requires Python 3.10 or higher.
echo  Current version: !PY_VER!
echo  Please upgrade from https://www.python.org/downloads/
echo.
pause & exit /b 1

:python_ok
echo  [OK]  Python !PY_VER! found.
echo.

:: ============================================================
::  STEP 2 -- Create .venv if absent
:: ============================================================
echo [STEP 2/9] Checking virtual environment...
echo.

set "FRESH_VENV=0"
if not exist "%VENV_PYTHON%" (
    echo  [INFO] .venv not found -- creating inside streamlit_app\
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [FAIL] Could not create virtual environment.
        echo.
        echo  ERROR: 'python -m venv' failed.
        echo.
        echo  Possible causes:
        echo    - The 'venv' module is missing. Run: python -m pip install virtualenv
        echo    - Disk permission issue: try running this bat as Administrator
        echo    - Antivirus blocking file creation in: %VENV_DIR%
        echo.
        pause & exit /b 1
    )
    set "FRESH_VENV=1"
    echo  [OK]  .venv created at: %VENV_DIR%
) else (
    echo  [OK]  .venv already exists at: %VENV_DIR%
)
echo.

:: Upgrade pip quietly
echo  [INFO] Upgrading pip (silently)...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet --no-warn-script-location 2>nul
echo  [OK]  pip up-to-date.
echo.

:: ============================================================
::  STEP 3 -- Install / sync dependencies
:: ============================================================
echo [STEP 3/9] Checking dependencies...
echo.

set "NEED_INSTALL=0"

if "!FRESH_VENV!"=="1" (
    set "NEED_INSTALL=1"
    echo  [INFO] Fresh venv -- will install all packages.
)

:: Check stamp file vs requirements modification timestamps
set "STAMP=%VENV_DIR%\requirements.stamp"
if not exist "%STAMP%" (
    set "NEED_INSTALL=1"
    echo  [WARN] No stamp file found -- will verify packages.
)

if "!NEED_INSTALL!"=="0" (
    for %%f in ("%STREAMLIT_DIR%\requirements.txt") do set "REQ_TS=%%~tf"
    for %%f in ("%BACKEND_DIR%\requirements.txt")   do set "BREQ_TS=%%~tf"
    for %%f in ("%STAMP%")                           do set "STAMP_TS=%%~tf"

    if "!REQ_TS!" GTR "!STAMP_TS!" (
        set "NEED_INSTALL=1"
        echo  [WARN] streamlit_app\requirements.txt changed -- updating packages.
    )
    if "!BREQ_TS!" GTR "!STAMP_TS!" (
        set "NEED_INSTALL=1"
        echo  [WARN] backend\requirements.txt changed -- updating packages.
    )
)

if "!NEED_INSTALL!"=="0" (
    echo  [INFO] requirements unchanged -- running quick import check...
    "%VENV_PYTHON%" -c "import streamlit, fastapi, neo4j, uvicorn" 2>nul
    if errorlevel 1 (
        echo  [WARN] Import check failed -- some packages may be broken. Reinstalling.
        set "NEED_INSTALL=1"
    ) else (
        echo  [OK]  All key packages healthy -- skipping install.
        echo.
    )
)

if "!NEED_INSTALL!"=="1" goto :run_install
goto :deps_done

:run_install
echo.
echo  [INFO] Installing streamlit_app\requirements.txt...
echo         (First run may take several minutes -- large ML packages)
echo.
"%VENV_PIP%" install -r "%STREAMLIT_DIR%\requirements.txt"
if errorlevel 1 (
    echo.
    echo [FAIL] Package install failed for streamlit_app\requirements.txt
    echo.
    echo  ERROR: pip could not install one or more packages.
    echo.
    echo  Common causes:
    echo    - No internet connection
    echo    - Corporate proxy / firewall blocking PyPI
    echo      Fix: pip config set global.index-url https://pypi.org/simple
    echo    - Disk full
    echo    - Incompatible Python version for a binary wheel
    echo.
    echo  Read the pip error above to find the specific failing package.
    pause & exit /b 1
)
echo.
echo  [OK]  streamlit_app packages installed.
echo.

echo  [INFO] Installing backend\requirements.txt...
"%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    echo.
    echo [FAIL] Package install failed for backend\requirements.txt
    echo.
    echo  ERROR: pip could not install one or more backend packages.
    echo  Check the error above for the specific failing package.
    pause & exit /b 1
)
echo.
echo  [OK]  backend packages installed.

:: Write stamp
echo %date% %time% > "%STAMP%"
echo.

:deps_done

:: ============================================================
::  STEP 4 -- Verify critical imports
:: ============================================================
echo [STEP 4/9] Verifying critical imports...
echo.

set "IMPORT_FAIL=0"
for %%m in (streamlit fastapi neo4j uvicorn) do (
    "%VENV_PYTHON%" -c "import %%m" 2>nul
    if errorlevel 1 (
        echo  [FAIL] Cannot import '%%m'
        set "IMPORT_FAIL=1"
    ) else (
        echo  [OK]   %%m
    )
)

if "!IMPORT_FAIL!"=="1" (
    echo.
    echo  ERROR: One or more critical packages failed to import.
    echo.
    echo  How to fix:
    echo    1. Delete the .venv folder: %VENV_DIR%
    echo    2. Re-run this batch file for a clean install
    echo.
    pause & exit /b 1
)
echo.

:: ============================================================
::  STEP 5 -- Locate Neo4j
:: ============================================================
echo [STEP 5/9] Locating Neo4j...
echo.

set "NEO4J_BAT="

:: Check Neo4j Desktop managed DBMS directory (most common on dev machines)
set "DESKTOP_DATA=%USERPROFILE%\.Neo4jDesktop2\Data\dbmss"
if exist "%DESKTOP_DATA%" (
    for /d %%d in ("%DESKTOP_DATA%\*") do (
        if exist "%%d\bin\neo4j.bat" set "NEO4J_BAT=%%d\bin\neo4j.bat"
    )
)

:: Check Neo4j Desktop cache directory (fallback)
set "DESKTOP_CACHE=%USERPROFILE%\.Neo4jDesktop2\Cache\dbmss"
if exist "%DESKTOP_CACHE%" (
    for /d %%d in ("%DESKTOP_CACHE%\*") do (
        if exist "%%d\bin\neo4j.bat" set "NEO4J_BAT=%%d\bin\neo4j.bat"
    )
)

:: Check portable install bundled inside project folder
if "%NEO4J_BAT%"=="" if exist "%ROOT%\neo4j\bin\neo4j.bat"          set "NEO4J_BAT=%ROOT%\neo4j\bin\neo4j.bat"
if "%NEO4J_BAT%"=="" if exist "%ROOT%\neo4j_local\bin\neo4j.bat"    set "NEO4J_BAT=%ROOT%\neo4j_local\bin\neo4j.bat"

:: Check common system-wide install paths
if "%NEO4J_BAT%"=="" if exist "C:\neo4j\bin\neo4j.bat"                             set "NEO4J_BAT=C:\neo4j\bin\neo4j.bat"
if "%NEO4J_BAT%"=="" if exist "C:\Program Files\Neo4j\bin\neo4j.bat"               set "NEO4J_BAT=C:\Program Files\Neo4j\bin\neo4j.bat"
if "%NEO4J_BAT%"=="" if exist "C:\Program Files (x86)\Neo4j\bin\neo4j.bat"         set "NEO4J_BAT=C:\Program Files (x86)\Neo4j\bin\neo4j.bat"

if "%NEO4J_BAT%"=="" (
    echo  [FAIL] neo4j.bat not found.
    echo.
    echo  ERROR: Could not auto-locate a Neo4j installation.
    echo.
    echo  Searched:
    echo    - %DESKTOP_DATA%\*\bin\neo4j.bat
    echo    - %DESKTOP_CACHE%\*\bin\neo4j.bat
    echo    - %ROOT%\neo4j\bin\neo4j.bat
    echo    - C:\neo4j\bin\neo4j.bat
    echo    - C:\Program Files\Neo4j\bin\neo4j.bat
    echo.
    echo  How to fix:
    echo    Option A: Install Neo4j Desktop (https://neo4j.com/download/)
    echo              and create a local DBMS, then re-run this bat.
    echo    Option B: Download Neo4j Community, extract to:
    echo              %ROOT%\neo4j\
    echo              then re-run.
    echo    Option C: Edit this batch file: find the line "set NEO4J_BAT="
    echo              and set it to the full path of your neo4j.bat
    echo.
    pause & exit /b 1
)
echo  [OK]  Neo4j found: %NEO4J_BAT%
echo.

:: ============================================================
::  STEP 6 -- Start Neo4j (if not already running)
:: ============================================================
echo [STEP 6/9] Starting Neo4j...
echo.

call :port_in_use %NEO4J_BOLT_PORT% NEO4J_UP
if "!NEO4J_UP!"=="1" (
    echo  [INFO] Neo4j Bolt port %NEO4J_BOLT_PORT% already listening -- skipping start.
    echo.
) else (
    echo  [INFO] Launching Neo4j in a background window...
    echo         Logs: %NEO4J_LOG%
    echo.
    start "Neo4j Server" /MIN cmd /c ""%NEO4J_BAT%" console > "%NEO4J_LOG%" 2>&1"

    echo  [INFO] Waiting for Neo4j (timeout 90s)...
    set "NEO4J_READY=0"
    for /L %%i in (1,1,90) do (
        if "!NEO4J_READY!"=="0" (
            call :port_in_use %NEO4J_BOLT_PORT% _CHK
            if "!_CHK!"=="1" (
                set "NEO4J_READY=1"
                echo  [OK]  Neo4j ready after %%i second(s^).
            ) else (
                timeout /t 1 /nobreak >nul
                set /a "_DOT=%%i %% 10"
                if "!_DOT!"=="0" echo  [....] Still waiting (%%i/90 s^)...
            )
        )
    )

    if "!NEO4J_READY!"=="0" (
        echo.
        echo  [FAIL] Neo4j did not start within 90 seconds.
        echo.
        echo  ERROR: Neo4j startup timed out.
        echo.
        echo  Possible causes:
        echo    - Java not installed or wrong version (need Java 17 or 21)
        echo      Check: java -version
        echo    - Port %NEO4J_BOLT_PORT% blocked by another process
        echo      Check: netstat -ano ^| findstr ":%NEO4J_BOLT_PORT%"
        echo    - Trial license expired
        echo    - neo4j.conf has bad settings
        echo.
        echo  Check log: %NEO4J_LOG%
        echo  Tip: Run "%NEO4J_BAT% console" manually to see full output.
        echo.
        pause & exit /b 1
    )
    echo.
)

:: ============================================================
::  STEP 7 -- Verify Neo4j driver connection
:: ============================================================
echo [STEP 7/9] Verifying Neo4j connection...
echo.

:: Write a tiny helper script so we avoid cmd line-continuation quoting issues
set "CHK_PY=%TEMP%\amc_neo4j_check.py"
(
    echo import sys, os
    echo from dotenv import load_dotenv
    echo load_dotenv(r"%STREAMLIT_DIR%\.env"^)
    echo from neo4j import GraphDatabase
    echo uri = os.getenv("NEO4J_URI", "bolt://localhost:7687"^)
    echo user = os.getenv("NEO4J_USER", "neo4j"^)
    echo pwd  = os.getenv("NEO4J_PASSWORD", ""^)
    echo try:
    echo     d = GraphDatabase.driver(uri, auth=(user, pwd^), connection_timeout=10^)
    echo     d.verify_connectivity(^)
    echo     d.close(^)
    echo     print("CONNECTION_OK"^)
    echo except Exception as e:
    echo     print(f"CONNECTION_FAIL: {e}"^)
    echo     sys.exit(1^)
) > "%CHK_PY%"

"%VENV_PYTHON%" "%CHK_PY%" 2>&1 | findstr "CONNECTION_OK" >nul

if errorlevel 1 (
    echo  [FAIL] Python neo4j driver cannot connect.
    echo.
    echo  ERROR: Neo4j appears to be running (port open) but the
    echo         driver could not authenticate or connect.
    echo.
    echo  Possible causes:
    echo    - Wrong credentials in streamlit_app\.env
    echo      File: %STREAMLIT_DIR%\.env
    echo      Keys: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    echo    - Neo4j is still initializing -- wait 10 s and retry
    echo    - neo4j.conf has dbms.connector.bolt.listen_address
    echo      pointing to a non-localhost address
    echo.
    pause & exit /b 1
)
echo  [OK]  Neo4j connection and authentication verified.
echo.

:: ============================================================
::  STEP 8 -- Start FastAPI backend
:: ============================================================
echo [STEP 8/9] Starting FastAPI backend (port %API_PORT%)...
echo.

call :port_in_use %API_PORT% API_UP
if "!API_UP!"=="1" (
    echo  [WARN] Port %API_PORT% already in use -- killing stale process...
    for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%API_PORT% " ^| findstr "LISTENING"') do (
        taskkill /PID %%p /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

start "FastAPI Backend" /MIN cmd /c "cd /d "%BACKEND_DIR%" && "%VENV_PYTHON%" -m uvicorn app.main:app --host 0.0.0.0 --port %API_PORT% > "%API_LOG%" 2>&1"

echo  [INFO] Waiting for FastAPI /api/status (timeout 60s)...
set "API_READY=0"
for /L %%i in (1,1,60) do (
    if "!API_READY!"=="0" (
        "%VENV_PYTHON%" -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:%API_PORT%/api/status',timeout=1); sys.exit(0)" >nul 2>&1
        if not errorlevel 1 (
            set "API_READY=1"
            echo  [OK]  FastAPI ready after %%i second(s^).
        ) else (
            timeout /t 1 /nobreak >nul
            set /a "_ADOT=%%i %% 10"
            if "!_ADOT!"=="0" echo  [....] Still waiting (%%i/60 s^)...
        )
    )
)

if "!API_READY!"=="0" (
    echo  [WARN] FastAPI /api/status did not respond within 60 s.
    echo         Backend may still be loading ML models.
    echo         Streamlit will start anyway -- it degrades gracefully.
    echo         Check: %API_LOG%
    echo.
) else (
    echo.
)

:: ============================================================
::  STEP 9 -- Start Streamlit
:: ============================================================
echo [STEP 9/9] Starting Streamlit app (port %STREAMLIT_PORT%)...
echo.

call :port_in_use %STREAMLIT_PORT% ST_UP
if "!ST_UP!"=="1" (
    echo  [WARN] Port %STREAMLIT_PORT% already in use -- killing stale process...
    for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":%STREAMLIT_PORT% " ^| findstr "LISTENING"') do (
        taskkill /PID %%p /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

start "Streamlit App" /MIN cmd /c "cd /d "%STREAMLIT_DIR%" && "%VENV_STREAMLIT%" run app.py --server.port %STREAMLIT_PORT% --server.address 0.0.0.0 > "%STREAMLIT_LOG%" 2>&1"

echo  [INFO] Waiting for Streamlit (timeout 45s)...
set "ST_READY=0"
for /L %%i in (1,1,45) do (
    if "!ST_READY!"=="0" (
        call :port_in_use %STREAMLIT_PORT% _STCHK
        if "!_STCHK!"=="1" (
            set "ST_READY=1"
            echo  [OK]  Streamlit ready after %%i second(s^).
        ) else (
            timeout /t 1 /nobreak >nul
            set /a "_SDOT=%%i %% 10"
            if "!_SDOT!"=="0" echo  [....] Still waiting (%%i/45 s^)...
        )
    )
)

if "!ST_READY!"=="0" (
    echo.
    echo  [FAIL] Streamlit did not start within 45 seconds.
    echo.
    echo  ERROR: Streamlit failed to bind port %STREAMLIT_PORT%.
    echo.
    echo  Possible causes:
    echo    - Import error in app.py or a view module
    echo    - A dependency is still missing from .venv
    echo    - Firewall or antivirus blocking port %STREAMLIT_PORT%
    echo.
    echo  Check log: %STREAMLIT_LOG%
    echo.
    pause & exit /b 1
)

:: Open browser after 1 s
timeout /t 1 /nobreak >nul
start "" "http://localhost:%STREAMLIT_PORT%"

:: ============================================================
::  SUCCESS SUMMARY
:: ============================================================
echo.
echo ============================================================
echo   ALL SERVICES ARE RUNNING
echo ============================================================
echo.
echo   Streamlit (main app)   --  http://localhost:%STREAMLIT_PORT%
echo   FastAPI backend docs   --  http://localhost:%API_PORT%/docs
echo   FastAPI status         --  http://localhost:%API_PORT%/api/status
echo   Neo4j Browser          --  http://localhost:%NEO4J_HTTP_PORT%
echo.
echo   Log files are in: %LOG_DIR%
echo     neo4j.log      -- Neo4j server output
echo     api.log        -- FastAPI / uvicorn output
echo     streamlit.log  -- Streamlit output
echo.
echo ============================================================
echo   Press any key in this window to SHUT DOWN everything.
echo   (Closing this window leaves all services running.)
echo ============================================================
echo.
pause >nul

:: ── Graceful shutdown ──────────────────────────────────────────────────
echo.
echo  [INFO] Shutting down services...
taskkill /FI "WINDOWTITLE eq FastAPI Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Streamlit App*"   /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Neo4j Server*"    /T /F >nul 2>&1
echo  [OK]  All services stopped. Goodbye.
echo.
endlocal
exit /b 0


:: ============================================================
::  SUBROUTINE  port_in_use <port> <out_var>
::  Sets <out_var>=1 if something is LISTENING on <port>, else 0
:: ============================================================
:port_in_use
set "%~2=0"
netstat -ano 2>nul | findstr /C:":%~1 " | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 set "%~2=1"
exit /b 0
