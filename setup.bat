@echo off
setlocal
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=py -3"
%PY% --version >nul 2>nul || (echo Python 3 not found. Install it from python.org and tick "Add to PATH". & goto :fail)

echo Installing Python packages...
%PY% -m pip install --quiet pygame-ce pywin32 numpy || goto :fail

for /f "delims=" %%i in ('%PY% find_terraria.py') do set "TERRARIA_DIR=%%i"
if "%TERRARIA_DIR%"=="" (echo Terraria not found. Set TERRARIA_DIR to your Terraria folder and rerun. & goto :fail)
echo Found Terraria at %TERRARIA_DIR%

set "GAC=C:\Windows\Microsoft.NET\assembly\GAC_32"
set "XNA=v4.0_4.0.0.0__842cf8be1de50553"
if not exist "%GAC%\Microsoft.Xna.Framework\%XNA%\Microsoft.Xna.Framework.dll" (
  echo Installing the XNA 4.0 runtime from the Terraria folder...
  msiexec /i "%TERRARIA_DIR%\xnafx40_redist.msi" /passive || goto :fail
)

echo Building texture exporter...
C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe /nologo /platform:x86 /target:exe /out:tools\XnbExport.exe ^
  /r:"%GAC%\Microsoft.Xna.Framework\%XNA%\Microsoft.Xna.Framework.dll" ^
  /r:"%GAC%\Microsoft.Xna.Framework.Game\%XNA%\Microsoft.Xna.Framework.Game.dll" ^
  /r:"%GAC%\Microsoft.Xna.Framework.Graphics\%XNA%\Microsoft.Xna.Framework.Graphics.dll" ^
  tools\XnbExport.cs || goto :fail

echo Exporting textures...
tools\XnbExport.exe "%TERRARIA_DIR%\Content" "%~dp0assets" tools\assets.txt || goto :fail
echo Done. Run play.bat to start.
exit /b 0

:fail
echo Setup failed.
pause
exit /b 1
