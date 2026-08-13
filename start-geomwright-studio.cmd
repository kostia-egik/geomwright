@echo off
setlocal EnableExtensions
title Geomwright Studio

pushd "%~dp0" >nul || goto :path_error

if defined KOMPAS_UI_PYTHON (
  set "PYTHON_EXE=%KOMPAS_UI_PYTHON%"
) else (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
)

if exist "%PYTHON_EXE%" goto :check_python
if defined KOMPAS_UI_PYTHON goto :python_missing

echo [Geomwright Studio] First launch: creating the local .venv environment...
where py >nul 2>nul
if errorlevel 1 goto :try_python
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :try_python
py -3 -m venv ".venv"
if not errorlevel 1 goto :check_python

:try_python
where python >nul 2>nul
if errorlevel 1 goto :python_missing
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :python_missing
python -m venv ".venv"
if errorlevel 1 goto :setup_failed

:check_python
"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :python_version

"%PYTHON_EXE%" -c "from importlib.metadata import version; from pathlib import Path; import fastapi, geomwright, jinja2, uvicorn; assert version('geomwright'); assert Path(geomwright.__file__).resolve().is_relative_to((Path.cwd() / 'src').resolve())" >nul 2>nul
if not errorlevel 1 goto :run

echo [Geomwright Studio] Installing UI components. This is required only once...
"%PYTHON_EXE%" -m pip install --disable-pip-version-check -e ".[ui]"
if errorlevel 1 goto :setup_failed

:run
echo.
echo [Geomwright Studio] Starting the interface...
echo [Geomwright Studio] Keep this window open. Press Ctrl+C or close it to stop the server.
echo.
"%PYTHON_EXE%" -m geomwright.studio %*
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" goto :finish
echo.
echo [Geomwright Studio] The server stopped with error %EXIT_CODE%.
pause
goto :finish

:path_error
echo [Geomwright Studio] Could not open the project directory.
set "EXIT_CODE=1"
pause
goto :finish_without_popd

:python_missing
echo [Geomwright Studio] Python 3.11 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/ and try again.
set "EXIT_CODE=1"
pause
goto :finish

:python_version
echo [Geomwright Studio] Python 3.11 or newer is required. The current .venv is incompatible.
set "EXIT_CODE=1"
pause
goto :finish

:setup_failed
echo.
echo [Geomwright Studio] Environment setup failed. Check your internet connection
echo and run start-geomwright-studio.cmd again.
set "EXIT_CODE=1"
pause

:finish
popd >nul

:finish_without_popd
endlocal & exit /b %EXIT_CODE%
