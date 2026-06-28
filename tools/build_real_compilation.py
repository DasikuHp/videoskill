#!/usr/bin/env python3
"""Download real video clips and assemble a fast-cut compilation — end to end.

This is the "even from a locked-down box" path: it pulls real footage from
GitHub-hosted sources (reachable when YouTube/archive.org are blocked by egress
policy), validates each clip decodes, then runs fast_cut_montage to build a real
compilation where no shot is held longer than the cut ceiling (<=2.5s, 3s max).

Usage:
    python3 tools/build_real_compilation.py --output outputs/real_compilation.mp4
    python3 tools/build_real_compilation.py --manifest tools/clip_sources.json --max-cut 2.5
    python3 tools/build_real_compilation.py --urls https://.../a.mp4 https://.../b.mp4

Sources in the default manifest are CC / open / CV-test footage. To use your own
viral clips, point --manifest at your list or pass --urls. Respect copyright.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit  # noqa: E402

TOOLS = Path(__file__).resolve().parent


def _log(msg: str) -> None:
    print(f"[build_real_compilation] {msg}", file=sys.stderr, flush=True)


def _download_one(url: str, name: str, work: Path) -> tuple[Path | None, str]:
    """Use video_downloader.py --direct so the download path is shared/tested."""
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "video_downloader.py"),
         "--direct", "--url", url, "--name", name, "--output-dir", str(work)],
        capture_output=True, text=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT: "):
            try:
                r = json.loads(line[len("RESULT: "):])
            except json.JSONDecodeError:
                continue
            if r.get("status") == "succeeded":
                arts = r.get("artifacts") or []
                if arts:
                    return Path(arts[0]["path"]), ""
            return None, r.get("error", "download failed")
    return None, (proc.stderr.strip()[-200:] or "no RESULT from downloader")


def main() -> None:
    ap = argparse.ArgumentParser(prog="build_real_compilation.py")
    ap.add_argument("--manifest", default=str(TOOLS / "clip_sources.json"))
    ap.add_argument("--urls", nargs="*", help="direct clip URLs (overrides manifest)")
    ap.add_argument("--output", default="outputs/real_compilation.mp4")
    ap.add_argument("--max-cut", type=float, default=2.5)
    ap.add_argument("--work-dir", default="tmp/video_jobs/real_compilation/source")
    args = ap.parse_args()

    # build the download list
    if args.urls:
        items = [{"url": u, "name": f"clip_{i:02d}.mp4"} for i, u in enumerate(args.urls)]
    else:
        try:
            manifest = json.loads(Path(args.manifest).read_text())
        except Exception as exc:
            emit({"status": "failed", "stage": "build_compilation", "error": f"manifest: {exc}"})
            sys.exit(2)
        items = manifest.get("clips", [])
    if not items:
        emit({"status": "failed", "stage": "build_compilation", "error": "no clips to download"})
        sys.exit(2)

    work = Path(args.work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)

    started = time.time()
    downloaded: list[str] = []
    failures: list[dict] = []
    for i, it in enumerate(items):
        name = it.get("name") or f"clip_{i:02d}.mp4"
        _log(f"downloading {i+1}/{len(items)}: {name}")
        path, err = _download_one(it["url"], name, work)
        if path:
            downloaded.append(str(path))
        else:
            failures.append({"url": it["url"], "error": err})
            _log(f"  FAILED: {err}")

    if not downloaded:
        emit({"status": "failed", "stage": "build_compilation",
              "error": "all downloads failed", "failures": failures})
        sys.exit(1)

    _log(f"assembling {len(downloaded)} clips with fast_cut_montage (max_cut={args.max_cut})")
    out_path = Path(args.output).resolve()
    proc = subprocess.run(
        [sys.executable, str(TOOLS / "fast_cut_montage.py"), "clips", *downloaded,
         "--output", str(out_path), "--max-cut", str(args.max_cut)],
        capture_output=True, text=True,
    )
    montage = None
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT: "):
            try:
                montage = json.loads(line[len("RESULT: "):])
            except json.JSONDecodeError:
                pass
    if not montage or montage.get("status") != "succeeded":
        emit({"status": "failed", "stage": "build_compilation",
              "error": (montage or {}).get("error", proc.stderr.strip()[-300:]),
              "downloaded": downloaded, "failures": failures})
        sys.exit(1)

    emit({
        "status": "succeeded", "stage": "build_compilation",
        "artifacts": montage.get("artifacts", []),
        "metrics": {**montage.get("metrics", {}),
                    "clips_downloaded": len(downloaded),
                    "clips_failed": len(failures),
                    "total_elapsed_s": round(time.time() - started, 1)},
        "downloaded": downloaded,
        "failures": failures,
        "next_action": "review outputs and (optionally) add captions/hooks per clip",
    })


if __name__ == "__main__":
    main()
