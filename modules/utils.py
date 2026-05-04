from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"


def load_config(path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def configure_logging(level: str = "INFO") -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def require_binary(binary: str) -> str:
    if "/" in binary:
        path = resolve_project_path(binary)
        if path.exists():
            return str(path)
        raise RuntimeError(f"Required executable not found: {path}")

    resolved = shutil.which(binary)
    if not resolved:
        raise RuntimeError(f"Required executable not found on PATH: {binary}")
    return resolved


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def truncate_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "."
