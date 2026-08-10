@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Installing Python dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/3] Building CutFlowBatch.exe...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CutFlowBatch main.py
if errorlevel 1 goto :error

echo [3/3] Copying local FFmpeg tools when available...
if exist "ffmpeg.exe" copy /Y "ffmpeg.exe" "dist\ffmpeg.exe" >nul
if exist "ffprobe.exe" copy /Y "ffprobe.exe" "dist\ffprobe.exe" >nul

echo.
echo Build completed: %CD%\dist\CutFlowBatch.exe
exit /b 0

:error
echo.
echo Build failed. Review the messages above.
exit /b 1

