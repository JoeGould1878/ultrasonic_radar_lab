"""
Shared reader for main/app_config.h, used by every sim/ script.

Implementation: Claude (Anthropic), for Joe Gould. No code adapted.

Every sim takes its defaults from the firmware's own config, so when a value
in app_config.h changes, re-running the sim updates the evidence. Numbers are
never copied into a script by hand.

    from appcfg import parse_config, CONFIG_H
    cfg = parse_config(CONFIG_H, needed=["APP_SWEEP_STEP_DEG", ...])
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_H = ROOT / "main" / "app_config.h"
EVIDENCE_SIM = ROOT / "docs" / "evidence" / "sim"

_DEFINE = re.compile(r"^\s*#define\s+(APP_\w+)\s+(-?\d+(?:\.\d+)?)f?\b")


def parse_config(path: Path = CONFIG_H, needed: list[str] | None = None) -> dict[str, float]:
    """Read every numeric `#define APP_...` from app_config.h.

    Exits with a message naming any `needed` define that is missing, so a
    renamed macro fails loudly instead of silently using a stale number.
    """
    vals: dict[str, float] = {}
    for line in path.read_text().splitlines():
        m = _DEFINE.match(line)
        if m:
            vals[m.group(1)] = float(m.group(2))
    missing = [n for n in (needed or []) if n not in vals]
    if missing:
        sys.exit(f"{path.name} is missing: {', '.join(missing)}")
    return vals
