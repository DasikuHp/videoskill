#!/usr/bin/env python3
"""Generate viral hook variants for short-form / avatar-explainer videos.

A hook is the first 1-2 spoken lines (the first ~3 seconds) that decide whether
a viewer keeps watching. This tool turns a topic (and optionally a transcript or
description) into a ranked set of hook variants across proven angles, plus a
matching on-screen text line for each. Emits one ``RESULT: {json}`` line.

It uses the OpenAI API (OPENAI_API_KEY). Output is structured JSON so the agent
can pick a hook and feed it straight into the avatar script.

Usage:
    python3 viral_hooks.py --topic "Google's new AI Mode for SEO" --platform tiktok --count 8
    python3 viral_hooks.py --topic "..." --transcript-file source.srt
    python3 viral_hooks.py --topic "..." --output tmp/video_jobs/foo/hooks.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import emit  # noqa: E402


DEFAULT_MODEL = "gpt-4o"  # widely-available text model; override with --model for newer

HOOK_ANGLES = [
    "curiosity-gap (open a loop the viewer must close)",
    "contrarian (challenge a common belief)",
    "stat-shock (lead with a surprising number)",
    "stakes (what the viewer loses by not knowing)",
    "story-tease (a concrete person mid-situation)",
    "direct-callout (name the exact audience)",
    "before/after (the transformation)",
    "question (a sharp question they can't not answer)",
]

SYSTEM = (
    "You are a short-form video hook writer. You write the first spoken line(s) "
    "that stop the scroll in the first 3 seconds. Hooks must be concrete, specific, "
    "and honest — no clickbait that the video can't pay off, no fake claims, no "
    "'you won't believe'. Match the platform's native voice. Keep spoken hooks to "
    "1-2 short sentences a real person can say in ~3 seconds."
)


def _read_optional(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    return p.read_text(encoding="utf-8", errors="replace")[:6000] if p.exists() else ""


def _build_prompt(args, transcript: str) -> str:
    parts = [
        f"Topic: {args.topic}",
        f"Platform: {args.platform}",
        f"Tone: {args.tone}",
        f"Write {args.count} distinct viral hook variants.",
        "Use a different angle for each, drawn from: " + "; ".join(HOOK_ANGLES) + ".",
    ]
    if transcript:
        parts.append("Source transcript/description to ground the hooks (do not invent facts beyond it):\n" + transcript)
    parts.append(
        "Return STRICT JSON only, no prose, shaped exactly as:\n"
        '{"hooks":[{"angle":"...","spoken":"...","on_screen_text":"...",'
        '"why_it_works":"...","predicted_strength":1-10}]}'
        "\nSort hooks by predicted_strength descending."
    )
    return "\n\n".join(parts)


def generate(args) -> None:
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        emit({"status": "failed", "stage": "viral_hooks", "error": "OPENAI_API_KEY missing in .env"})
        sys.exit(2)

    from openai import OpenAI

    transcript = _read_optional(args.transcript_file)
    user_prompt = _build_prompt(args, transcript)
    client = OpenAI()

    try:
        print(f"[viral_hooks] {args.count} hooks for '{args.topic[:60]}' on {args.platform}", file=sys.stderr)
        resp = client.chat.completions.create(
            model=args.model,
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as exc:
        emit({"status": "failed", "stage": "viral_hooks", "error": str(exc), "model": args.model})
        sys.exit(1)

    hooks = data.get("hooks", []) if isinstance(data, dict) else []
    if not hooks:
        emit({"status": "failed", "stage": "viral_hooks", "error": "model returned no hooks", "raw": raw[:300]})
        sys.exit(1)

    out_path = None
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"topic": args.topic, "platform": args.platform, "hooks": hooks}, indent=2))

    emit({
        "status": "succeeded", "stage": "viral_hooks",
        "topic": args.topic, "platform": args.platform,
        "count": len(hooks), "hooks": hooks,
        "artifacts": ([{"type": "json", "path": str(out_path)}] if out_path else []),
        "next_action": "pick the top hook and use it as the avatar script's first line",
    })


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="viral_hooks.py")
    p.add_argument("--topic", required=True)
    p.add_argument("--platform", default="tiktok",
                   choices=["tiktok", "reels", "shorts", "youtube", "linkedin", "x"])
    p.add_argument("--tone", default="confident, fast, editorial")
    p.add_argument("--count", type=int, default=8)
    p.add_argument("--transcript-file", help="optional .srt/.txt to ground hooks in real content")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--output", default="", help="optional path to save hooks.json")
    p.set_defaults(func=generate)
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
