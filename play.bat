@echo off
cd /d "%~dp0"
if not exist assets\Images_Tiles_0.png call setup.bat || exit /b 1
where pythonw >nul 2>nul && (start "" pythonw game.py) || (start "" pyw -3 game.py)
