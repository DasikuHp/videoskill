#!/usr/bin/env python3
"""OpenAI image generation/editing helper for video assets.

This is intentionally small: agents call this script instead of writing raw API
calls. It saves outputs locally and emits one RESULT JSON line.
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_MODEL = "gpt-image-2"  # current model as of 2026-04-21 (snapshot gpt-image-2-2026-04-21)
DEFAULT_SIZE = "2048x1152"     # native 16:9, both edges multiples of 16 (skill default for full-frame stills)


def validate_size(size: str) -> tuple[bool, str]:
    """Validate a size string against gpt-image-2 constraints.

    Rules (per OpenAI docs): both edges multiples of 16, max edge 3840,
    aspect ratio <= 3:1, total pixels between 655,360 and 8,294,400.
    "auto" is always allowed.
    """
    if size == "auto":
        return True, ""
    try:
        w, h = (int(v) for v in size.lower().split("x"))
    except Exception:
        return False, f"Size '{size}' must look like WIDTHxHEIGHT (e.g. 2048x1152) or 'auto'."
    if w % 16 or h % 16:
        return False, f"Both edges of '{size}' must be multiples of 16."
    if max(w, h) > 3840:
        return False, f"Max edge of '{size}' must be <= 3840."
    if not (1 / 3 <= w / h <= 3):
        return False, f"Aspect ratio of '{size}' must be within 3:1."
    if not (655_360 <= w * h <= 8_294_400):
        return False, f"Total pixels of '{size}' must be between 655,360 and 8,294,400."
    return True, ""


def emit(payload):
    print("RESULT: " + json.dumps(payload), flush=True)


def output_dir():
    out = Path.cwd() / "output_images"
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_b64_image(b64_data, prefix="image"):
    path = output_dir() / f"{prefix}_{int(time.time())}.png"
    path.write_bytes(base64.b64decode(b64_data))
    return path


def generate(args):
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        emit({"status": "failed", "error": "OPENAI_API_KEY missing in .env", "provider": "openai"})
        sys.exit(2)

    ok, why = validate_size(args.size)
    if not ok:
        emit({"status": "failed", "provider": "openai", "error": why})
        sys.exit(2)

    from openai import OpenAI  # lazy: validate args before requiring the SDK
    client = OpenAI()
    try:
        print(f"[image_provider] Generating image with {args.model} ({args.size}, q={args.quality}): {args.prompt[:120]}", file=sys.stderr)
        result = client.images.generate(
            model=args.model,
            prompt=args.prompt,
            size=args.size,
            quality=args.quality,
        )
        item = result.data[0]
        b64_data = getattr(item, "b64_json", None)
        if not b64_data:
            emit({"status": "failed", "error": "No b64_json returned by image API", "provider": "openai"})
            sys.exit(1)
        path = save_b64_image(b64_data, "openai_image")
        emit({
            "status": "succeeded",
            "provider": "openai",
            "model": args.model,
            "prompt": args.prompt,
            "size": args.size,
            "local_path": str(path),
        })
    except Exception as exc:
        emit({"status": "failed", "error": str(exc), "provider": "openai", "model": args.model})
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--prompt", required=True)
    gen.add_argument("--size", default=DEFAULT_SIZE, help="WIDTHxHEIGHT (edges multiple of 16) or 'auto'")
    gen.add_argument("--quality", default="high", choices=["low", "medium", "high", "auto", "standard"])
    gen.add_argument("--model", default=DEFAULT_MODEL)
    gen.set_defaults(func=generate)
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
