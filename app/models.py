from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class VideoItem:
    """A video queued for processing."""

    path: Path
    duration: float | None = None
    status: str = "Ожидает"


@dataclass(slots=True)
class ProcessingSummary:
    successful: int = 0
    errors: int = 0
    skipped: int = 0
    cancelled: bool = False

