"""Where API keys come from: the process environment, then `.env` in the repo root, then (macOS only) the Keychain."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _dotenv() -> dict[str, str]:
    path = REPO / ".env"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        out[name.removeprefix("export ").strip()] = value.strip().strip("'\"")
    return out


def get(name: str) -> str:
    """The value of `name`, or "" when it is set nowhere."""
    value = os.environ.get(name) or _dotenv().get(name, "")
    if value or sys.platform != "darwin":
        return value
    r = subprocess.run(["security", "find-generic-password", "-s", name, "-w"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""
