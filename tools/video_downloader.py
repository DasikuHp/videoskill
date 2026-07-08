#!/usr/bin/env python3
"""Download source videos for repurposing (yt-dlp wrapper).

Pulls a video (YouTube, TikTok, X, Vimeo, direct URL, ...) into the job folder
so it can be clipped, transcribed, captioned, and reframed. Emits one
``RESULT: {json}`` line so the agent can parse the local path as source-of-truth.

Usage:
    python3 video_downloader.py --url "https://youtu.be/..." --output-dir tmp/video_jobs/foo/source
    python3 video_downloader.py --url "..." --audio-only
    python3 video_downloader.py --url "..." --section "*00:01:00-00:02:30"
    python3 video_downloader.py --url "..." --info-only   # metadata only, no download

Respect copyright and platform Terms of Service. Only download content you have
the right to use.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit  # noqa: E402


def _ensure_yt_dlp() -> str:
    # vendored self-contained zipapp: works with any python3, no pip install
    vendored = Path(__file__).resolve().parent / "bin" / "yt-dlp"
    if vendored.is_file():
        return f"{sys.executable} {vendored}"
    exe = shutil.which("yt-dlp")
    if exe:
        return exe
    # fall back to module form if installed as a library only
    try:
        import yt_dlp  # noqa: F401
        return f"{sys.executable} -m yt_dlp"
    except Exception:
        emit({"status": "failed", "stage": "download",
              "error": "yt-dlp not installed. `pip install yt-dlp`."})
        sys.exit(2)


def _ffprobe_ok(path: Path) -> tuple[bool, dict]:
    """Confirm a file is a real, decodable video with a video stream."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,codec_name",
         "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return False, {}
    try:
        data = json.loads(proc.stdout)
        st = (data.get("streams") or [{}])[0]
        dur = float(data.get("format", {}).get("duration") or 0)
        return bool(st.get("codec_name")) and dur > 0, {
            "width": st.get("width"), "height": st.get("height"),
            "codec": st.get("codec_name"), "duration_seconds": round(dur, 2),
        }
    except Exception:
        return False, {}


def cmd_direct(args: argparse.Namespace) -> None:
    """Stream a direct video URL (e.g. raw.githubusercontent.com) over HTTPS.

    More reliable than yt-dlp for plain file URLs and works wherever the egress
    policy allows the host (GitHub is commonly allowed even when YouTube is not).
    """
    import urllib.request

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or Path(args.url.split("?")[0]).name or f"clip_{int(time.time())}.mp4"
    dest = out_dir / name

    started = time.time()
    try:
        # urllib honors HTTPS_PROXY/HTTP_PROXY from the environment.
        req = urllib.request.Request(args.url, headers={"User-Agent": "super-video-maker/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as exc:
        emit({"status": "failed", "stage": "download", "error": f"{type(exc).__name__}: {exc}", "url": args.url})
        sys.exit(1)

    ok, meta = _ffprobe_ok(dest)
    if not ok:
        emit({"status": "failed", "stage": "download",
              "error": "downloaded file is not a decodable video", "path": str(dest)})
        sys.exit(1)

    emit({
        "status": "succeeded", "stage": "download",
        "artifacts": [{"type": "video", "path": str(dest)}],
        "metrics": {**meta, "size_mb": round(dest.stat().st_size / (1024 * 1024), 2),
                    "elapsed_s": round(time.time() - started, 1)},
        "next_action": "feed into fast_cut_montage.py clips",
    })


def cmd_download(args: argparse.Namespace) -> None:
    yt = _ensure_yt_dlp().split()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.info_only:
        proc = subprocess.run(
            [*yt, "--dump-single-json", "--no-warnings", args.url],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            emit({"status": "failed", "stage": "download",
                  "error": (proc.stderr.strip() or "yt-dlp --dump-json failed")[-400:]})
            sys.exit(1)
        try:
            meta = json.loads(proc.stdout)
        except json.JSONDecodeError:
            emit({"status": "failed", "stage": "download", "error": "could not parse yt-dlp metadata"})
            sys.exit(1)
        emit({
            "status": "succeeded", "stage": "download_info",
            "info": {
                "id": meta.get("id"),
                "title": meta.get("title"),
                "duration_seconds": meta.get("duration"),
                "uploader": meta.get("uploader"),
                "view_count": meta.get("view_count"),
                "like_count": meta.get("like_count"),
                "upload_date": meta.get("upload_date"),
                "webpage_url": meta.get("webpage_url"),
                "description": (meta.get("description") or "")[:1000],
            },
            "next_action": "download (drop --info-only) or generate hooks from the title/description",
        })
        return

    # Stable, predictable output name based on title/id; print final path via --print.
    out_template = str(out_dir / "%(title).80s-%(id)s.%(ext)s")
    cmd = [*yt, "--no-playlist", "--no-warnings", "--restrict-filenames",
           "-o", out_template, "--print", "after_move:filepath"]

    if args.audio_only:
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        # cap height, prefer mp4, remux to mp4 so downstream FFmpeg is happy
        cmd += ["-f", f"bv*[height<={args.max_height}]+ba/b[height<={args.max_height}]/b",
                "--merge-output-format", "mp4", "--remux-video", "mp4"]

    if args.section:
        cmd += ["--download-sections", args.section, "--force-keyframes-at-cuts"]
    if args.write_subs:
        cmd += ["--write-auto-subs", "--write-subs", "--sub-langs", args.sub_langs, "--convert-subs", "srt"]

    cmd.append(args.url)

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        emit({"status": "failed", "stage": "download",
              "error": (proc.stderr.strip() or "yt-dlp failed")[-500:]})
        sys.exit(1)

    printed = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    local_path = printed[-1] if printed else ""
    if not local_path or not Path(local_path).exists():
        # fall back to newest file in the dir
        files = sorted(out_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        local_path = str(files[0]) if files else ""

    if not local_path:
        emit({"status": "failed", "stage": "download", "error": "download finished but no file found"})
        sys.exit(1)

    size_mb = round(Path(local_path).stat().st_size / (1024 * 1024), 2)
    emit({
        "status": "succeeded", "stage": "download",
        "artifacts": [{"type": "audio" if args.audio_only else "video", "path": local_path}],
        "metrics": {"size_mb": size_mb, "elapsed_s": round(time.time() - started, 1)},
        "next_action": "transcribe (video_captioner) or generate viral hooks",
    })


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="video_downloader.py")
    p.add_argument("--url", required=True)
    p.add_argument("--output-dir", default="tmp/video_jobs/downloads")
    p.add_argument("--max-height", type=int, default=1080)
    p.add_argument("--audio-only", action="store_true")
    p.add_argument("--section", help="yt-dlp --download-sections expr, e.g. '*00:01:00-00:02:30'")
    p.add_argument("--write-subs", action="store_true", help="also fetch subtitles/auto-captions")
    p.add_argument("--sub-langs", default="en")
    p.add_argument("--info-only", action="store_true", help="print metadata only, no download")
    p.add_argument("--direct", action="store_true",
                   help="stream a plain file URL over HTTPS (e.g. raw.githubusercontent.com) instead of yt-dlp")
    p.add_argument("--name", help="output filename for --direct")
    return p


def main() -> None:
    args = build_parser().parse_args()
    if args.direct:
        cmd_direct(args)
    else:
        cmd_download(args)


if __name__ == "__main__":
    main()
