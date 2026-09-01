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

:: -- Project root is where this .bat lives --------------------------------
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

:: -- Make log directory ---------------------------------------------------
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo ============================================================
echo   AMC Context-Engineering -- Portable Launcher
echo ============================================================
echo.

:: ------------------------------------------------------------------------
::  Guard: project structure check
:: ------------------------------------------------------------------------
if not exist "%STREAMLIT_DIR%\app.py" goto :err_no_streamlit
if not exist "%BACKEND_DIR%\app\main.py" goto :err_no_backend

:: ============================================================
::  STEP 1 -- Validate Python 3.10+
:: ============================================================
echo [STEP 1/9] Checking Python...
echo.

where python >nul 2>&1
if errorlevel 1 goto :err_no_python

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 goto :err_python_old

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo  [OK]  %PY_VER% found.
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
    if errorlevel 1 goto :err_venv_failed
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

set "STAMP=%VENV_DIR%\requirements.stamp"
if not exist "%STAMP%" (
    set "NEED_INSTALL=1"
    echo  [WARN] No stamp file found -- will verify packages.
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
if errorlevel 1 goto :err_pip_streamlit
echo.
echo  [OK]  streamlit_app packages installed.
echo.

echo  [INFO] Installing backend\requirements.txt...
"%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 goto :err_pip_backend
echo.
echo  [OK]  backend packages installed.

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

if "!IMPORT_FAIL!"=="1" goto :err_import_fail
echo.

:: ============================================================
::  STEP 5 -- Locate Neo4j
:: ============================================================
echo [STEP 5/9] Locating Neo4j...
echo.

set "NEO4J_BAT=C:\Users\Laptopadmin\.Neo4jDesktop2\Data\dbmss\dbms-49637bb0-9857-4a15-80ce-c71aa9f2ed6b\bin\neo4j.bat"

if not exist "%NEO4J_BAT%" (
    set "NEO4J_BAT="

    set "DESKTOP_DATA=%USERPROFILE%\.Neo4jDesktop2\Data\dbmss"
    if exist "%DESKTOP_DATA%" (
        for /d %%d in ("%DESKTOP_DATA%\*") do (
            if exist "%%d\bin\neo4j.bat" set "NEO4J_BAT=%%d\bin\neo4j.bat"
        )
    )

    set "DESKTOP_CACHE=%USERPROFILE%\.Neo4jDesktop2\Cache\dbmss"
    if exist "%DESKTOP_CACHE%" (
        for /d %%d in ("%DESKTOP_CACHE%\*") do (
            if exist "%%d\bin\neo4j.bat" set "NEO4J_BAT=%%d\bin\neo4j.bat"
        )
    )

    if "%NEO4J_BAT%"=="" if exist "%ROOT%\neo4j\bin\neo4j.bat"          set "NEO4J_BAT=%ROOT%\neo4j\bin\neo4j.bat"
    if "%NEO4J_BAT%"=="" if exist "%ROOT%\neo4j_local\bin\neo4j.bat"    set "NEO4J_BAT=%ROOT%\neo4j_local\bin\neo4j.bat"

    if "%NEO4J_BAT%"=="" if exist "C:\neo4j\bin\neo4j.bat"                             set "NEO4J_BAT=C:\neo4j\bin\neo4j.bat"
    if "%NEO4J_BAT%"=="" if exist "C:\Program Files\Neo4j\bin\neo4j.bat"               set "NEO4J_BAT=C:\Program Files\Neo4j\bin\neo4j.bat"
    if "%NEO4J_BAT%"=="" if exist "C:\Program Files (x86)\Neo4j\bin\neo4j.bat"         set "NEO4J_BAT=C:\Program Files (x86)\Neo4j\bin\neo4j.bat"
)

if "%NEO4J_BAT%"=="" goto :err_no_neo4j
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
    goto :neo4j_done
)

echo  [INFO] Launching Neo4j in a background window...
echo         Logs: %NEO4J_LOG%
echo.

REM Create temporary wrapper script to avoid quoting issues
set "_WRAPPER=%TEMP%\neo4j_start.bat"
call :write_neo4j_wrapper

start "Neo4j Server" /MIN cmd /c "!_WRAPPER!"

echo  [INFO] Waiting for Neo4j (timeout 90s)...
set "NEO4J_READY=0"
for /L %%i in (1,1,90) do (
    if "!NEO4J_READY!"=="0" (
        call :port_in_use %NEO4J_BOLT_PORT% _CHK
        if "!_CHK!"=="1" (
            set "NEO4J_READY=1"
            echo  [OK]  Neo4j ready after %%i second^s.
        ) else (
            timeout /t 1 /nobreak >nul
            set /a "_DOT=%%i %% 10"
            if "!_DOT!"=="0" echo  [....] Still waiting %%i/90 s...
        )
    )
)

if "!NEO4J_READY!"=="0" goto :err_neo4j_timeout

:neo4j_done
echo.

:: ============================================================
::  STEP 7 -- Verify Neo4j driver connection
:: ============================================================
echo [STEP 7/9] Verifying Neo4j connection...
echo.

set "CHK_PY=%TEMP%\amc_neo4j_check.py"
echo import sys, os > "%CHK_PY%"
echo from dotenv import load_dotenv >> "%CHK_PY%"
echo load_dotenv(r"%STREAMLIT_DIR%\.env") >> "%CHK_PY%"
echo from neo4j import GraphDatabase >> "%CHK_PY%"
echo uri = os.getenv("NEO4J_URI", "bolt://localhost:7687") >> "%CHK_PY%"
echo user = os.getenv("NEO4J_USER", "neo4j") >> "%CHK_PY%"
echo pwd  = os.getenv("NEO4J_PASSWORD", "") >> "%CHK_PY%"
echo try: >> "%CHK_PY%"
echo     d = GraphDatabase.driver(uri, auth=(user, pwd), connection_timeout=10) >> "%CHK_PY%"
echo     d.verify_connectivity() >> "%CHK_PY%"
echo     d.close() >> "%CHK_PY%"
echo     print("CONNECTION_OK") >> "%CHK_PY%"
echo except Exception as e: >> "%CHK_PY%"
echo     print(f"CONNECTION_FAIL: {e}") >> "%CHK_PY%"
echo     sys.exit(1) >> "%CHK_PY%"

"%VENV_PYTHON%" "%CHK_PY%" 2>&1 | findstr "CONNECTION_OK" >nul
if errorlevel 1 goto :err_neo4j_auth
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
        if not "%%p"=="" taskkill /PID %%p /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

REM Create temporary wrapper script to avoid quoting issues
set "_API_WRAPPER=%TEMP%\fastapi_start.bat"
call :write_api_wrapper

start "FastAPI Backend" /MIN cmd /c "!_API_WRAPPER!"

echo  [INFO] Waiting for FastAPI /api/status (timeout 60s)...
set "API_READY=0"
for /L %%i in (1,1,60) do (
    if "!API_READY!"=="0" (
        "%VENV_PYTHON%" -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:%API_PORT%/api/status',timeout=1); sys.exit(0)" >nul 2>&1
        if not errorlevel 1 (
            set "API_READY=1"
            echo  [OK]  FastAPI ready after %%i second^s.
        ) else (
            timeout /t 1 /nobreak >nul
            set /a "_ADOT=%%i %% 10"
            if "!_ADOT!"=="0" echo  [....] Still waiting %%i/60 s...
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
        if not "%%p"=="" taskkill /PID %%p /F >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
)

REM Create temporary wrapper script to avoid quoting issues
set "_ST_WRAPPER=%TEMP%\streamlit_start.bat"
call :write_st_wrapper

start "Streamlit App" /MIN cmd /c "!_ST_WRAPPER!"

echo  [INFO] Waiting for Streamlit (timeout 45s)...
set "ST_READY=0"
for /L %%i in (1,1,45) do (
    if "!ST_READY!"=="0" (
        call :port_in_use %STREAMLIT_PORT% _STCHK
        if "!_STCHK!"=="1" (
            set "ST_READY=1"
            echo  [OK]  Streamlit ready after %%i second^s.
        ) else (
            timeout /t 1 /nobreak >nul
            set /a "_SDOT=%%i %% 10"
            if "!_SDOT!"=="0" echo  [....] Still waiting %%i/45 s...
        )
    )
)

if "!ST_READY!"=="0" goto :err_streamlit_timeout

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

:: -- Graceful shutdown --------------------------------------------------
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
::  SUBROUTINES AND ERROR LABELS
:: ============================================================

:port_in_use
set "%~2=0"
netstat -ano 2>nul | findstr /C:":%~1 " | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 set "%~2=1"
exit /b 0

:write_neo4j_wrapper
(
    echo @echo off
    echo call "!NEO4J_BAT!" console ^> "!NEO4J_LOG!" 2^>^&1
) > "!_WRAPPER!"
exit /b 0

:write_api_wrapper
(
    echo @echo off
    echo cd /d "!BACKEND_DIR!"
    echo "!VENV_PYTHON!" -m uvicorn app.main:app --host 0.0.0.0 --port %API_PORT% ^> "!API_LOG!" 2^>^&1
) > "!_API_WRAPPER!"
exit /b 0

:write_st_wrapper
(
    echo @echo off
    echo cd /d "!STREAMLIT_DIR!"
    echo "!VENV_STREAMLIT!" run app.py --server.port %STREAMLIT_PORT% --server.address 0.0.0.0 ^> "!STREAMLIT_LOG!" 2^>^&1
) > "!_ST_WRAPPER!"
exit /b 0

:err_no_streamlit
echo [FAIL] Cannot find: %STREAMLIT_DIR%\app.py
echo.
echo  ERROR: This batch file must sit in the project ROOT folder.
pause & exit /b 1

:err_no_backend
echo [FAIL] Cannot find: %BACKEND_DIR%\app\main.py
echo.
echo  ERROR: backend folder appears incomplete or missing.
pause & exit /b 1

:err_no_python
echo [FAIL] Python not found on PATH.
echo.
echo  ERROR: Python 3.10 or later is required but was not found.
pause & exit /b 1

:err_python_old
echo [FAIL] Python 3.10+ required.
echo.
echo  ERROR: Current Python version is older than 3.10.
pause & exit /b 1

:err_venv_failed
echo [FAIL] Could not create virtual environment.
pause & exit /b 1

:err_pip_streamlit
echo [FAIL] Package install failed for streamlit_app\requirements.txt
pause & exit /b 1

:err_pip_backend
echo [FAIL] Package install failed for backend\requirements.txt
pause & exit /b 1

:err_import_fail
echo ERROR: One or more critical packages failed to import.
pause & exit /b 1

:err_no_neo4j
echo  [FAIL] neo4j.bat not found.
echo.
echo  ERROR: Could not auto-locate a Neo4j installation.
pause & exit /b 1

:err_neo4j_timeout
echo.
echo  [FAIL] Neo4j did not start within 90 seconds.
echo  Check log: %NEO4J_LOG%
pause & exit /b 1

:err_neo4j_auth
echo  [FAIL] Python neo4j driver cannot connect.
echo.
echo  ERROR: Neo4j is running but driver could not authenticate.
echo  Check credentials in: %STREAMLIT_DIR%\.env
pause & exit /b 1

:err_streamlit_timeout
echo.
echo  [FAIL] Streamlit did not start within 45 seconds.
echo  Check log: %STREAMLIT_LOG%
pause & exit /b 1
