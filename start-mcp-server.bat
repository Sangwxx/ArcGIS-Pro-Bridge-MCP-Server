@echo off
setlocal enabledelayedexpansion

rem ────────────────────────────────────────────
rem  ArcGIS Pro Bridge MCP Server Launcher
rem  for Claude Desktop / Cursor / Trae
rem ────────────────────────────────────────────

cd /d "%~dp0"

rem -- locate uv --------------------------------------------------
set UV_EXE=
where uv >nul 2>&1
if %errorlevel% equ 0 (
    set UV_EXE=uv
) else if exist "%USERPROFILE%\.local\bin\uv.exe" (
    set UV_EXE=%USERPROFILE%\.local\bin\uv.exe
) else if exist "%LOCALAPPDATA%\Programs\uv\uv.exe" (
    set UV_EXE=%LOCALAPPDATA%\Programs\uv\uv.exe
) else if exist "C:\Users\%USERNAME%\.cargo\bin\uv.exe" (
    set UV_EXE=C:\Users\%USERNAME%\.cargo\bin\uv.exe
)

if "%UV_EXE%"=="" (
    echo [arcgis-mcp] ERROR: uv not found.
    echo.
    echo uv is required to run this server.
    echo Install it from: https://github.com/astral-sh/uv
    echo Or add "%USERPROFILE%\.local\bin" to your system PATH.
    echo.
    exit /b 1
)

rem -- run server -------------------------------------------------
"%UV_EXE%" run arcgis_mcp_server.py
exit /b %errorlevel%
