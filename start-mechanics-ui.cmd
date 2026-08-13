@echo off
echo [Geomwright] start-mechanics-ui.cmd is deprecated; use start-geomwright-studio.cmd.
call "%~dp0start-geomwright-studio.cmd" %*
exit /b %ERRORLEVEL%
