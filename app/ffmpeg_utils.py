from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .settings import application_directory


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def find_binary(name: str) -> str | None:
    """Find an FFmpeg binary beside the app first, then in PATH."""

    executable_name = f"{name}.exe" if os.name == "nt" else name
    local_candidate = application_directory() / executable_name
    if local_candidate.is_file():
        return str(local_candidate)
    return shutil.which(executable_name) or shutil.which(name)


def find_ffmpeg_tools() -> tuple[str | None, str | None]:
    return find_binary("ffmpeg"), find_binary("ffprobe")


def popen_command(command: Sequence[str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )


def probe_duration_command(ffprobe_path: str, input_path: Path) -> list[str]:
    return [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(input_path),
    ]


def parse_probe_duration(stdout: str) -> float:
    try:
        duration = float(json.loads(stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("FFprobe не вернул корректную длительность видео.") from exc
    if duration <= 0:
        raise ValueError("Длительность видео должна быть больше нуля.")
    return duration


def copy_trim_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    trim_start: float,
    new_duration: float,
) -> list[str]:
    return [
        ffmpeg_path,
        "-hide_banner",
        "-y",
        "-ss",
        format_seconds(trim_start),
        "-i",
        str(input_path),
        "-t",
        format_seconds(new_duration),
        "-map",
        "0",
        "-c",
        "copy",
        str(output_path),
    ]


def transcode_trim_command(
    ffmpeg_path: str,
    input_path: Path,
    output_path: Path,
    trim_start: float,
    new_duration: float,
) -> list[str]:
    # Optional maps avoid failures for files without audio and omit streams that
    # cannot be represented reliably in an MP4 fallback (for example PGS subtitles).
    return [
        ffmpeg_path,
        "-hide_banner",
        "-y",
        "-ss",
        format_seconds(trim_start),
        "-i",
        str(input_path),
        "-t",
        format_seconds(new_duration),
        "-map",
        "0:v?",
        "-map",
        "0:a?",
        "-map_metadata",
        "0",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def format_seconds(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def concise_error(stderr: str, max_lines: int = 6) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    if not lines:
        return "FFmpeg завершился с неизвестной ошибкой."
    return " | ".join(lines[-max_lines:])

