from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


APP_NAME = "CutFlow Batch"
SETTINGS_FILENAME = "cutflow_settings.json"


def application_directory() -> Path:
    """Return the directory beside the script or bundled executable."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def default_output_directory() -> Path:
    return application_directory() / "output"


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or application_directory() / SETTINGS_FILENAME

    def load(self) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "output_directory": str(default_output_directory()),
            "trim_start": 0.0,
            "trim_end": 0.0,
        }
        try:
            if self.path.is_file():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    defaults.update(data)
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        return defaults

    def save(self, output_directory: str, trim_start: float, trim_end: float) -> bool:
        data = {
            "output_directory": output_directory,
            "trim_start": trim_start,
            "trim_end": trim_end,
        }
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

