@echo off
REM ===========================================================================
REM Repair Engine Startup Script (Windows)
REM Runs the amc-repair-engine microservice on port 8002
REM ===========================================================================

setlocal enabledelayedexpansion

REM Configuration
set PORT=%REPAIR_ENGINE_PORT%
if "%PORT%"=="" set PORT=8002

set HOST=%REPAIR_ENGINE_HOST%
if "%HOST%"=="" set HOST=0.0.0.0

set LOG_LEVEL=%LOG_LEVEL%
if "%LOG_LEVEL%"=="" set LOG_LEVEL=info

set RELOAD=%RELOAD%
if "%RELOAD%"=="" set RELOAD=true

REM Print header
echo.
echo ================================
echo   AMC Repair Engine
echo   Microservice Startup (Windows)
echo ================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% found

REM Check if virtual environment exists
if not exist "..\..\\.venv" (
    echo [WARNING] Virtual environment not found at ...\.venv
    echo [INFO] Please activate your virtual environment first:
    echo        ...\.venv\Scripts\activate.bat
    exit /b 1
)

REM Check if in venv
if "!VIRTUAL_ENV!"=="" (
    echo [INFO] Virtual environment not activated. Attempting to activate...
    call ..\..\\.venv\Scripts\activate.bat
    if errorlevel 1 (
        echo [ERROR] Could not activate venv
        exit /b 1
    )
)

REM Verify amc-repair-engine is installed
python -c "import amc_repair" >nul 2>&1
if errorlevel 1 (
    echo [INFO] amc-repair-engine not found. Installing from source...
    pip install -e .
    if errorlevel 1 (
        echo [ERROR] Failed to install amc-repair-engine
        exit /b 1
    )
)

echo [OK] amc-repair-engine module found

REM Check environment variables
echo.
echo Configuration:
echo   Port: %PORT%
echo   Host: %HOST%
echo   Log Level: %LOG_LEVEL%
echo   Auto-reload: %RELOAD%

REM Check Neo4j connectivity
echo.
echo Checking dependencies...

set NEO4J_URI=%NEO4J_URI%
if "%NEO4J_URI%"=="" set NEO4J_URI=bolt://localhost:7687

echo   Neo4j (%NEO4J_URI%): 
python -c "from neo4j import GraphDatabase; d=GraphDatabase.driver('%NEO4J_URI%', auth=('neo4j', 'amc@1234')); d.verify_connectivity(); d.close()" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Not reachable (will retry at startup^)
) else (
    echo [OK]
)

REM Start server
echo.
echo Starting Repair Engine...
echo [INFO] Listening on %HOST%:%PORT%
echo [INFO] API Docs: http://%HOST%:%PORT%/docs
echo.

if "%RELOAD%"=="true" (
    python -m uvicorn src.amc_repair.server:app ^
        --host %HOST% ^
        --port %PORT% ^
        --log-level %LOG_LEVEL% ^
        --reload
) else (
    python -m uvicorn src.amc_repair.server:app ^
        --host %HOST% ^
        --port %PORT% ^
        --log-level %LOG_LEVEL%
)

