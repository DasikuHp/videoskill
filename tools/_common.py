#!/usr/bin/env python3
"""Shared helpers for super-video-maker tools.

Centralizes the small pieces that were copy-pasted across tools:
- ``emit`` for the ``RESULT: {json}`` stage contract,
- ``find_repo_root`` for locating the project root,
- ``get_font`` for a cross-platform (Linux/macOS/Windows) font loader.

Tools import this defensively so they keep working even if run as a loose
script: ``from _common import emit`` with a sys.path fallback.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def emit(payload: Dict[str, Any]) -> None:
    """Print the single machine-readable stage line the skill contract expects."""
    print("RESULT: " + json.dumps(payload), flush=True)


def find_repo_root(start: Optional[Path] = None) -> Path:
    """Walk up from ``start`` (or cwd, then this file) to a .env/.git marker.

    The caller's project root wins so a user can invoke a tool from any project;
    falls back to the skill folder, then the start dir.
    """
    candidates = []
    cwd = Path.cwd().resolve()
    candidates.append(cwd)
    if start is not None:
        candidates.append(Path(start).resolve())
    candidates.append(Path(__file__).resolve().parent)

    for base in candidates:
        for path in [base, *base.parents]:
            if (path / ".env").exists() or (path / ".git").exists():
                return path
    return cwd


# Font candidates ordered Linux → macOS → Windows so the same code renders
# legible text on a VPS (where the rest of the pipeline runs) and on a laptop.
_REGULAR_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]
_BOLD_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]


def get_font(size: int, bold: bool = False):
    """Return a TrueType font of ``size`` that actually exists on this OS.

    Falls back to Pillow's bitmap default only when no system font is found.
    Imported lazily so tools that never draw don't need Pillow installed.
    """
    from PIL import ImageFont  # local import: not every tool needs Pillow

    for path in (_BOLD_FONTS if bold else _REGULAR_FONTS):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def ensure_on_path() -> None:
    """Add this tools/ dir to sys.path so sibling imports work when run directly."""
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
