@echo off
rem ScreenTutor: double-click to start. The black window stays minimised in the taskbar;
rem closing it closes ScreenTutor.
cd /d "%~dp0"
set PYTHONUTF8=1
start "ScreenTutor - dong cua so nay de tat" /min py -m screentutor.app
