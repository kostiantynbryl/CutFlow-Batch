from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from .ffmpeg_utils import (
    concise_error,
    copy_trim_command,
    parse_probe_duration,
    popen_command,
    probe_duration_command,
    transcode_trim_command,
)
from .models import ProcessingSummary, VideoItem


class VideoProcessor(QObject):
    log = Signal(str)
    current_file = Signal(str)
    item_updated = Signal(int, object, str)
    progress = Signal(int, int)
    finished = Signal(object)

    def __init__(
        self,
        items: list[VideoItem],
        output_directory: Path,
        trim_start: float,
        trim_end: float,
        ffmpeg_path: str,
        ffprobe_path: str,
    ) -> None:
        super().__init__()
        self.items = items
        self.output_directory = output_directory
        self.trim_start = trim_start
        self.trim_end = trim_end
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._cancel_event = threading.Event()
        self._process_lock = threading.Lock()
        self._current_process: subprocess.Popen[str] | None = None

    def request_cancel(self) -> None:
        """May safely be called directly from the GUI thread."""

        self._cancel_event.set()
        with self._process_lock:
            process = self._current_process
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass

    @Slot()
    def run(self) -> None:
        summary = ProcessingSummary()
        total = len(self.items)
        self.progress.emit(0, total)

        try:
            self.output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.log.emit(f"Ошибка: не удалось создать папку вывода: {exc}")
            summary.errors = total
            self.finished.emit(summary)
            return

        for index, item in enumerate(self.items):
            if self._cancel_event.is_set():
                summary.cancelled = True
                break

            self.current_file.emit(item.path.name)
            self.item_updated.emit(index, item.duration, "Обработка")
            self.log.emit(f"Начата обработка: {item.path}")

            if not item.path.is_file():
                summary.errors += 1
                self.item_updated.emit(index, item.duration, "Ошибка")
                self.log.emit(f"Ошибка: файл не найден: {item.path}")
                self.progress.emit(index + 1, total)
                continue

            try:
                duration = self._probe_duration(item.path)
                item.duration = duration
                self.item_updated.emit(index, duration, "Обработка")
            except CancelledError:
                summary.cancelled = True
                break
            except (OSError, RuntimeError) as exc:
                summary.errors += 1
                self.item_updated.emit(index, None, "Ошибка")
                self.log.emit(f"Ошибка FFprobe для «{item.path.name}»: {exc}")
                self.progress.emit(index + 1, total)
                continue

            new_duration = duration - self.trim_start - self.trim_end
            if new_duration <= 0:
                summary.skipped += 1
                self.item_updated.emit(index, duration, "Пропущен")
                self.log.emit(
                    f"Файл пропущен: «{item.path.name}». Сумма обрезки "
                    f"({self.trim_start + self.trim_end:g} сек) больше или равна "
                    f"длительности ({duration:.3f} сек)."
                )
                self.progress.emit(index + 1, total)
                continue

            output_path = unique_output_path(self.output_directory, item.path.stem)
            copy_command = copy_trim_command(
                self.ffmpeg_path,
                item.path,
                output_path,
                self.trim_start,
                new_duration,
            )
            try:
                return_code, stderr = self._run_command(copy_command)
                if return_code != 0:
                    remove_partial_file(output_path)
                    self.log.emit(
                        f"Copy-режим не удался для «{item.path.name}». "
                        "Используется fallback с перекодированием."
                    )
                    fallback_command = transcode_trim_command(
                        self.ffmpeg_path,
                        item.path,
                        output_path,
                        self.trim_start,
                        new_duration,
                    )
                    return_code, fallback_stderr = self._run_command(fallback_command)
                    if return_code != 0:
                        remove_partial_file(output_path)
                        raise RuntimeError(concise_error(fallback_stderr or stderr))
            except CancelledError:
                remove_partial_file(output_path)
                summary.cancelled = True
                self.item_updated.emit(index, duration, "Отменён")
                break
            except (OSError, RuntimeError) as exc:
                remove_partial_file(output_path)
                summary.errors += 1
                self.item_updated.emit(index, duration, "Ошибка")
                self.log.emit(f"Ошибка обработки «{item.path.name}»: {exc}")
                self.progress.emit(index + 1, total)
                continue

            summary.successful += 1
            self.item_updated.emit(index, duration, "Готово")
            self.log.emit(f"Успешно сохранено: {output_path}")
            self.progress.emit(index + 1, total)

        if self._cancel_event.is_set():
            summary.cancelled = True
            self.log.emit("Обработка отменена пользователем.")
        self.current_file.emit("—")
        self.finished.emit(summary)

    def _probe_duration(self, input_path: Path) -> float:
        return_code, stderr, stdout = self._communicate(
            probe_duration_command(self.ffprobe_path, input_path)
        )
        if self._cancel_event.is_set():
            raise CancelledError
        if return_code != 0:
            raise RuntimeError(concise_error(stderr))
        try:
            return parse_probe_duration(stdout)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

    def _run_command(self, command: list[str]) -> tuple[int, str]:
        return_code, stderr, _stdout = self._communicate(command)
        if self._cancel_event.is_set():
            raise CancelledError
        return return_code, stderr

    def _communicate(self, command: list[str]) -> tuple[int, str, str]:
        if self._cancel_event.is_set():
            raise CancelledError
        process = popen_command(command)
        with self._process_lock:
            self._current_process = process
            cancelled = self._cancel_event.is_set()
            if cancelled and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
        try:
            stdout, stderr = process.communicate()
            if cancelled:
                raise CancelledError
            return process.returncode, stderr, stdout
        finally:
            with self._process_lock:
                if self._current_process is process:
                    self._current_process = None


class CancelledError(Exception):
    pass


def unique_output_path(output_directory: Path, source_stem: str) -> Path:
    candidate = output_directory / f"{source_stem}_cut.mp4"
    counter = 1
    while candidate.exists():
        candidate = output_directory / f"{source_stem}_cut_{counter}.mp4"
        counter += 1
    return candidate


def remove_partial_file(path: Path) -> None:
    try:
        if path.exists():
            os.remove(path)
    except OSError:
        pass
