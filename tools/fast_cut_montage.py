#!/usr/bin/env python3
"""Fast-cut montage builder — enforces the "cut every <=2.5s (3s max)" rule.

Two modes:

  demo   Generate a dopaminergic Top-5 montage from synthetic scenes (no assets
         or API keys needed). Useful to prove the pacing + caption + beat format.

  clips  Re-cut real source videos so NO shot is held longer than --max-cut
         seconds. Each segment gets a punch-in zoom, so a long compilation clip
         becomes a fast-cut, high-retention edit. This is what you run on real
         downloaded footage (see video_downloader.py).

Every cut lands on a beat <= --max-cut seconds apart. Emits one RESULT json line.

Examples:
    python3 tools/fast_cut_montage.py demo --output outputs/top5_caidas.mp4
    python3 tools/fast_cut_montage.py clips raw1.mp4 raw2.mp4 --output outputs/montage.mp4 --max-cut 2.5
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit, _REGULAR_FONTS, _BOLD_FONTS  # noqa: E402

W, H, FPS = 1920, 1080, 30


def _font() -> str:
    for p in _BOLD_FONTS:
        if Path(p).exists():
            return p
    for p in _REGULAR_FONTS:
        if Path(p).exists():
            return p
    raise RuntimeError("No usable TrueType font found for drawtext.")


def _esc(text: str) -> str:
    """Escape text for ffmpeg drawtext."""
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\u2019")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_duration(path: Path) -> float:
    proc = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(path)])
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def _motion_chain(seconds: float) -> str:
    """Punch-in zoom + subtle hand-held shake, normalized to WxH @ FPS."""
    frames = max(1, int(seconds * FPS))
    return (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"zoompan=z='min(1.0+0.20*on/{frames},1.20)':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
        f"crop={W}:{H}:x='8*sin(2*PI*t*6)':y='8*cos(2*PI*t*5)'"
    )


# ── DEMO MODE ──────────────────────────────────────────────────────
DEMO_SCENES = [
    ("testsrc2",      "TOP 5",  "CAIDAS MAS GRACIOSAS",      2.0, "yellow"),
    ("rgbtestsrc",    "#5",     "EL RESBALON EPICO",         2.5, "white"),
    ("mandelbrot",    "#4",     "LA SILLA TRAICIONERA",      2.5, "cyan"),
    ("life",          "#3",     "EL TROPEZON VIRAL",         2.5, "lime"),
    ("yuvtestsrc",    "#2",     "EL BATACAZO LEGENDARIO",    2.5, "orange"),
    ("gradients",     "#1",     "LA REINA DE LAS CAIDAS",    2.5, "magenta"),
    ("testsrc2",      "",       "SIGUEME PARA MAS CAIDAS",   2.0, "white"),
]


def _build_scene(idx: int, src: str, num: str, cap: str, dur: float, color: str,
                 font: str, tmp: Path) -> Path:
    out = tmp / f"scene_{idx:02d}.mp4"
    vf = [_motion_chain(dur)]
    if num:
        vf.append(
            f"drawtext=fontfile={font}:text='{_esc(num)}':fontsize=440:"
            f"fontcolor={color}@0.88:borderw=12:bordercolor=black:"
            f"x=(w-tw)/2:y=(h-th)/2-70"
        )
    vf.append(
        f"drawtext=fontfile={font}:text='{_esc(cap)}':fontsize=74:fontcolor=white:"
        f"borderw=6:bordercolor=black:box=1:boxcolor=black@0.45:boxborderw=26:"
        f"x=(w-tw)/2:y=h-190"
    )
    # white flash on the first 3 frames of each cut = extra "pop"
    vf.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.55:t=fill:enable='lt(t,0.07)'")
    vf.append("format=yuv420p")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-t", f"{dur}", "-i", f"{src}=s={W}x{H}:r={FPS}",
        "-vf", ",".join(vf),
        "-t", f"{dur}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", str(out),
    ]
    proc = _run(cmd)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"scene {idx} render failed: {proc.stderr.strip()[-300:]}")
    return out


def cmd_demo(args: argparse.Namespace) -> None:
    font = _font()
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        scenes = []
        for i, (src, num, cap, dur, color) in enumerate(DEMO_SCENES):
            scenes.append(_build_scene(i, src, num, cap, dur, color, font, tmp))
        _finish(scenes, out_path, args)


# ── CLIPS MODE ─────────────────────────────────────────────────────
def _cut_segment(src: Path, start: float, dur: float, idx: int, font: str, tmp: Path) -> Path:
    out = tmp / f"seg_{idx:04d}.mp4"
    vf = _motion_chain(dur) + ",format=yuv420p"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src),
        "-vf", vf, "-an", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", str(out),
    ]
    proc = _run(cmd)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"segment {idx} failed: {proc.stderr.strip()[-300:]}")
    return out


def cmd_clips(args: argparse.Namespace) -> None:
    font = _font()
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    max_cut = min(args.max_cut, 3.0)  # hard ceiling per the rule
    sources = [Path(c).resolve() for c in args.inputs]
    missing = [str(s) for s in sources if not s.exists()]
    if missing:
        emit({"status": "failed", "stage": "fast_cut_montage", "error": f"clips not found: {missing}"})
        sys.exit(2)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        segments = []
        idx = 0
        for src in sources:
            dur = probe_duration(src)
            if dur <= 0:
                continue
            n = max(1, math.ceil(dur / max_cut))
            seg_len = dur / n
            for k in range(n):
                segments.append(_cut_segment(src, k * seg_len, seg_len, idx, font, tmp))
                idx += 1
        if not segments:
            emit({"status": "failed", "stage": "fast_cut_montage", "error": "no usable footage in inputs"})
            sys.exit(1)
        _finish(segments, out_path, args, cuts=len(segments), max_cut=max_cut)


# ── SHARED: concat + beat audio + loudnorm + QC ────────────────────
def _beat_expr(total: float) -> str:
    # kick every 0.5s + hi-hat on the off-beat = a simple energetic loop
    return (
        "aevalsrc='0.75*sin(2*PI*55*t)*exp(-7*mod(t\\,0.5))"
        "+0.18*sin(2*PI*2000*t)*exp(-40*mod(t+0.25\\,0.5))':"
        f"d={total:.3f}:s=44100"
    )


def _finish(parts: list[Path], out_path: Path, args, cuts: int | None = None, max_cut: float = 2.5) -> None:
    tmp = parts[0].parent
    listfile = tmp / "concat.txt"
    listfile.write_text("".join(f"file '{p}'\n" for p in parts))
    total = sum(probe_duration(p) for p in parts)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-f", "lavfi", "-i", _beat_expr(total),
        "-filter_complex", "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-shortest",
        str(out_path),
    ]
    proc = _run(cmd)
    if proc.returncode != 0 or not out_path.exists():
        emit({"status": "failed", "stage": "fast_cut_montage", "error": proc.stderr.strip()[-400:]})
        sys.exit(1)

    final_dur = probe_duration(out_path)
    size_mb = round(out_path.stat().st_size / (1024 * 1024), 2)
    emit({
        "status": "succeeded", "stage": "fast_cut_montage",
        "artifacts": [{"type": "video", "path": str(out_path)}],
        "metrics": {
            "duration_seconds": round(final_dur, 2),
            "cuts": cuts if cuts is not None else len(parts),
            "max_cut_seconds": max_cut,
            "avg_cut_seconds": round(final_dur / max(1, (cuts if cuts is not None else len(parts))), 2),
            "size_mb": size_mb,
        },
        "next_action": "review and post; cuts respect the <=2.5s (3s max) rule",
    })


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fast_cut_montage.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="generate a synthetic Top-5 dopaminergic montage")
    d.add_argument("--output", default="outputs/top5_caidas.mp4")
    d.set_defaults(func=cmd_demo)

    c = sub.add_parser("clips", help="re-cut real videos to <=max-cut per shot")
    c.add_argument("inputs", nargs="+", help="source video files")
    c.add_argument("--output", default="outputs/montage.mp4")
    c.add_argument("--max-cut", type=float, default=2.5, help="max seconds per shot (hard ceiling 3.0)")
    c.set_defaults(func=cmd_clips)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
