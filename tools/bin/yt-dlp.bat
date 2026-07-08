@echo off
rem Lanzador Windows del yt-dlp vendorizado (zipapp de Python).
rem Usa automaticamente el ffmpeg.exe/ffprobe.exe de esta misma carpeta.
rem Requiere Python 3.9+ (python.org o Microsoft Store).
setlocal
set "BIN=%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%BIN%yt-dlp" --ffmpeg-location "%BIN%." %*
) else (
    python "%BIN%yt-dlp" --ffmpeg-location "%BIN%." %*
)
endlocal
