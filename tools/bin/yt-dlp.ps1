# Lanzador PowerShell del yt-dlp vendorizado (zipapp de Python).
# Usa automaticamente el ffmpeg.exe/ffprobe.exe de esta misma carpeta.
# Requiere Python 3.9+ (python.org o Microsoft Store).
$bin = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $bin 'yt-dlp') --ffmpeg-location $bin @args
} else {
    & python (Join-Path $bin 'yt-dlp') --ffmpeg-location $bin @args
}
exit $LASTEXITCODE
