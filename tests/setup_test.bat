@echo off
REM OpenCode ArcGIS MCP Server Setup Test
REM Run this on Windows after copying arcgis-opencode-mcp to your machine

echo ========================================
echo ArcGIS OpenCode MCP Setup Test
echo ========================================
echo.

REM Check if Python is available
echo [1/5] Checking Python...
python --version
if errorlevel 1 (
    echo FAILED: Python not found in PATH
    exit /b 1
)
echo OK
echo.

REM Check if uv is available
echo [2/5] Checking uv package manager...
uv --version
if errorlevel 1 (
    echo uv not found - will use pip instead
    echo.
) else (
    echo OK
    echo.
)

REM Check if ArcGIS Pro Python exists
echo [3/5] Checking ArcGIS Pro Python...
if exist "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" (
    echo OK: Found ArcGIS Pro Python
) else (
    echo WARNING: Default ArcGIS Pro Python path not found
    echo Please update opencode.json with your Python path
)
echo.

REM Change to project root directory (where pyproject.toml and arcgis_mcp_server.py live)
pushd "%~dp0.."

REM Install dependencies
echo [4/5] Installing dependencies...
if exist "uv.lock" (
    uv sync
) else (
    pip install -e .
)
echo.

REM Test MCP server startup
echo [5/5] Testing MCP server...
echo Note: The server will wait for connections. Press Ctrl+C to exit.
echo.
python arcgis_mcp_server.py
echo.

echo ========================================
echo Setup test complete
echo ========================================

REM Return to original directory
popd

pause