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
    p.set_defaults(func=cmd_download)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
