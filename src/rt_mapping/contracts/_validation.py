"""Shared validation helpers for JSON metadata in data contracts.

Internal module: used by contracts.geometry and contracts.run_manifest.
"""

from __future__ import annotations

import math
from pathlib import PureWindowsPath
from typing import Any


def is_absolute_path(text: str) -> bool:
    """True for POSIX/Windows absolute or rooted paths, drive paths and ~ paths."""
    windows = PureWindowsPath(text)
    return bool(windows.drive or windows.root) or text.startswith("~")


def check_json_value(value: Any, where: str) -> None:
    """Recursively require JSON-compatible, finite values with string keys.

    Strings that are absolute paths are rejected (they leak host details).
    """
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if is_absolute_path(value):
            raise ValueError(f"{where} must not contain an absolute path, got {value!r}")
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{where} must be finite, got {value!r}")
        return
    if isinstance(value, list):
        for i, item in enumerate(value):
            check_json_value(item, f"{where}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{where} keys must be strings, got {key!r}")
            check_json_value(item, f"{where}[{key!r}]")
        return
    raise ValueError(f"{where} has a non-JSON value of type {type(value).__name__}")
