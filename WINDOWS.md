# Guía Windows — yt-dlp + ffmpeg vendorizados

> **Nota sobre el entorno de construcción**: esta herramienta se ensambló y
> verificó en un contenedor **Linux** (sesión de Claude Code en la nube). Ahí
> se probaron de extremo a extremo el zipapp `yt-dlp` y los binarios estáticos
> `ffmpeg`/`ffprobe` de Linux. Los ejecutables de Windows (`ffmpeg.exe`,
> `ffprobe.exe`) son los **builds oficiales win64 8.1.2 essentials de
> gyan.dev**, sin modificar; no se pudieron ejecutar en el contenedor por no
> haber Windows/Wine, así que esta guía es la versión para ti como usuario
> final de Windows.

## Qué hay en `tools\bin\`

| Fichero | Qué es |
|---|---|
| `yt-dlp` | zipapp de Python autocontenido (2026.07.04) — multiplataforma, también corre en Windows |
| `yt-dlp.bat` | **lanzador para CMD** — usa esto en Windows |
| `yt-dlp.ps1` | lanzador para PowerShell |
| `ffmpeg.exe`, `ffprobe.exe` | FFmpeg 8.1.2 win64 (gyan.dev), ya "junto a yt-dlp" como pide la doc oficial |
| `ffmpeg`, `ffprobe` | equivalentes estáticos para Linux (ignóralos en Windows) |

## Requisito único

Python 3.9 o superior: [python.org/downloads](https://www.python.org/downloads/)
o desde Microsoft Store (`python`). No hace falta pip, ni instalar ffmpeg, ni
clonar el repo de yt-dlp — todo está incluido.

## Uso (CMD)

```bat
cd tools\bin

:: Metadata en JSON sin descargar
yt-dlp.bat -j --no-warnings "https://youtu.be/..."

:: Mejor calidad hasta 1080p en mp4 (fusiona con el ffmpeg.exe incluido)
yt-dlp.bat -f "bv*[height<=1080]+ba/b[height<=1080]/b" --merge-output-format mp4 -o "%USERPROFILE%\Videos\%%(title).80s.%%(ext)s" "URL"

:: Solo audio mp3
yt-dlp.bat -x --audio-format mp3 --audio-quality 0 "URL"

:: Solo una sección
yt-dlp.bat --download-sections "*00:01:00-00:02:30" --force-keyframes-at-cuts "URL"
```

En PowerShell usa `.\yt-dlp.ps1` con los mismos argumentos (los `%%` de las
plantillas de salida pasan a ser `%` sueltos).

Los lanzadores añaden solos `--ffmpeg-location` apuntando a esta carpeta, así
que nunca necesitas pasarlo a mano.

## Uso desde las herramientas Python del repo

`tools\video_downloader.py` detecta Windows automáticamente: usa
`ffmpeg.exe`/`ffprobe.exe` vendorizados y el zipapp, sin configurar nada:

```bat
python tools\video_downloader.py --url "https://youtu.be/..." --info-only
```

## Notas

- ffprobe directo: `tools\bin\ffprobe.exe -v error -show_format -show_streams -of json video.mp4`
- Respeta el copyright y los Términos de Servicio de cada plataforma.
- Licencias GPL de FFmpeg en `tools\bin\LICENSE-ffmpeg-*.txt`.
