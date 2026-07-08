# Top 3 dopaminérgico — virales reales en ≤3 s

Clips de máximo 3 segundos con el pico dopaminérgico de tres virales
históricos reales, descargados y procesados íntegramente con las
herramientas vendorizadas del repo (`tools/bin/yt-dlp` + `ffmpeg`).

| # | Clip | Viral original | Momento elegido |
|---|------|----------------|-----------------|
| 1 | `1_dramatic_chipmunk.mp4` | Dramatic Chipmunk (2007) | El giro dramático con el sting musical (0.8–3.8 s del original) |
| 2 | `2_panda_estornudo.mp4` | Sneezing Baby Panda (2006) | Calma → estornudo → susto de la madre (10.3–13.3 s) |
| 3 | `3_charlie_ouch.mp4` | Charlie Bit My Finger (2007) | El mordisco fuerte y el "OUCH, Charlie!" (27.6–30.6 s) |

## Método que funciona para descargar virales "de verdad"

Desde entornos cloud/datacenter, YouTube (403 anti-bot en googlevideo) y
TikTok (bloqueo de IP) rechazan la descarga de datos. Lo que SÍ funciona:

1. **Mirrors de archive.org**: muchos virales clásicos están archivados con
   el patrón `https://archive.org/details/youtube-<ID_de_YouTube>`.
   Comprobar disponibilidad: `https://archive.org/metadata/youtube-<ID>`
   (JSON; si trae `files` con .mp4/.webm/.mkv, es descargable).
2. **Vimeo**: descarga directa sin bloqueo (probado con "The Mountain").
3. Descargar con el binario vendorizado:
   `python3 tools/bin/yt-dlp --ffmpeg-location tools/bin -f b -o "out.%(ext)s" "https://archive.org/details/youtube-<ID>"`

Desde una IP residencial (Windows del usuario), YouTube y TikTok funcionan
directamente con la misma herramienta.

## Pipeline del recorte

1. Localizar el pico dopaminérgico por sonoridad:
   `ffmpeg -af "asetnsamples=n=22050,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level" -f null -`
   (el grito/estornudo/sting marca el momento).
2. Verificar el fotograma del momento (`-ss <t> -frames:v 1`).
3. Cortar 3.0 s exactos: `-ss <inicio> -t 3` + saturación +15 %
   (`eq=saturation=1.15`) + loudness normalizado a -14 LUFS
   (`loudnorm=I=-14:TP=-1`), h264 crf 20 + aac.

Fuentes archivadas en archive.org; respeta el copyright de los originales
para cualquier uso más allá de pruebas técnicas.
