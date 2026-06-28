#!/usr/bin/env python3
"""Music provider adapter for video jobs.

The public skill supports multiple music backends. This script starts with a
safe local contract and leaves provider-specific endpoints behind adapters so
API changes do not break the skill instructions.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def emit(payload):
    print("RESULT: " + json.dumps(payload), flush=True)


ELEVEN_MUSIC_URL = "https://api.elevenlabs.io/v1/music"


def validate_elevenlabs(args):
    """Dry-run: confirm the key exists and echo the plan without spending credits."""
    load_dotenv()
    if not os.getenv("ELEVENLABS_API_KEY"):
        emit({"status": "failed", "provider": "elevenlabs", "error": "ELEVENLABS_API_KEY missing in .env"})
        sys.exit(2)
    emit({
        "status": "ready",
        "provider": "elevenlabs",
        "next_action": "Run `music_provider.py elevenlabs-generate` to actually compose the track.",
        "prompt": args.prompt,
        "duration_seconds": args.duration,
    })


def generate_elevenlabs(args):
    """Compose a real music track via the ElevenLabs Music API (POST /v1/music)."""
    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        emit({"status": "failed", "provider": "elevenlabs", "error": "ELEVENLABS_API_KEY missing in .env"})
        sys.exit(2)

    length_ms = int(args.duration * 1000)
    if not (3000 <= length_ms <= 600000):
        emit({"status": "failed", "provider": "elevenlabs",
              "error": "duration must be between 3 and 600 seconds"})
        sys.exit(2)

    import requests  # local import: only needed for real generation

    out_dir = Path.cwd() / "output_audio"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.output).resolve() if args.output else out_dir / f"music_{int(time.time())}.mp3"

    try:
        resp = requests.post(
            ELEVEN_MUSIC_URL,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"prompt": args.prompt, "music_length_ms": length_ms, "model_id": args.model_id},
            timeout=300,
        )
        resp.raise_for_status()
    except Exception as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        emit({"status": "failed", "provider": "elevenlabs", "error": str(exc),
              "detail": (detail or "")[:300]})
        sys.exit(1)

    out_path.write_bytes(resp.content)
    emit({
        "status": "succeeded",
        "provider": "elevenlabs",
        "model_id": args.model_id,
        "local_path": str(out_path),
        "duration_seconds": args.duration,
        "next_action": "Mix this file under voiceover with FFmpeg.",
    })


def use_existing(args):
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        emit({"status": "failed", "provider": "local", "error": f"Music file not found: {path}"})
        sys.exit(2)
    emit({
        "status": "succeeded",
        "provider": "local",
        "local_path": str(path),
        "next_action": "Mix this file under voiceover with FFmpeg.",
    })


def build_parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    eleven = sub.add_parser("elevenlabs-plan")
    eleven.add_argument("--prompt", required=True)
    eleven.add_argument("--duration", type=int, default=30)
    eleven.set_defaults(func=validate_elevenlabs)

    gen = sub.add_parser("elevenlabs-generate")
    gen.add_argument("--prompt", required=True)
    gen.add_argument("--duration", type=int, default=30, help="seconds (3-600)")
    gen.add_argument("--model-id", default="music_v2")
    gen.add_argument("--output", default="")
    gen.set_defaults(func=generate_elevenlabs)

    local = sub.add_parser("local")
    local.add_argument("--path", required=True)
    local.set_defaults(func=use_existing)

    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
