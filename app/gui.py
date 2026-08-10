from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTime, QTimer
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .ffmpeg_utils import find_ffmpeg_tools
from .models import ProcessingSummary, VideoItem
from .settings import SettingsStore, default_output_directory
from .video_processor import VideoProcessor


SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
VIDEO_FILTER = "Видео (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;Все файлы (*)"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings_store = SettingsStore()
        self.items: list[VideoItem] = []
        self.worker_thread: QThread | None = None
        self.worker: VideoProcessor | None = None
        self._close_after_finish = False

        self.setWindowTitle("CutFlow Batch — Mass Video Cut Tool")
        self.setMinimumSize(900, 680)
        self.resize(1060, 780)
        self._build_ui()
        self._apply_theme()
        self._restore_settings()
        self._set_processing_state(False)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 22)
        root.setSpacing(14)

        title = QLabel("CutFlow Batch")
        title.setObjectName("title")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        subtitle = QLabel("Mass Video Cut Tool")
        subtitle.setObjectName("subtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        file_actions = QHBoxLayout()
        self.add_button = QPushButton("Добавить видео")
        self.remove_button = QPushButton("Удалить выбранное")
        self.clear_button = QPushButton("Очистить список")
        file_actions.addWidget(self.add_button)
        file_actions.addWidget(self.remove_button)
        file_actions.addWidget(self.clear_button)
        file_actions.addStretch()
        root.addLayout(file_actions)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Файл", "Длительность", "Статус"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 3)

        settings_frame = QFrame()
        settings_frame.setObjectName("settingsFrame")
        settings_layout = QVBoxLayout(settings_frame)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setSpacing(12)

        output_row = QHBoxLayout()
        output_label = QLabel("Папка вывода")
        output_label.setMinimumWidth(140)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText(str(default_output_directory()))
        self.output_button = QPushButton("Выбрать папку вывода")
        output_row.addWidget(output_label)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_button)
        settings_layout.addLayout(output_row)

        trim_row = QHBoxLayout()
        trim_row.addWidget(QLabel("Обрезать начало, сек"))
        self.trim_start = self._make_seconds_input()
        trim_row.addWidget(self.trim_start)
        trim_row.addSpacing(24)
        trim_row.addWidget(QLabel("Обрезать конец, сек"))
        self.trim_end = self._make_seconds_input()
        trim_row.addWidget(self.trim_end)
        trim_row.addStretch()
        settings_layout.addLayout(trim_row)
        root.addWidget(settings_frame)

        process_row = QHBoxLayout()
        self.start_button = QPushButton("Старт")
        self.start_button.setObjectName("primaryButton")
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setObjectName("dangerButton")
        self.current_label = QLabel("Текущий файл: —")
        self.current_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        process_row.addWidget(self.start_button)
        process_row.addWidget(self.cancel_button)
        process_row.addWidget(self.current_label, 1)
        root.addLayout(process_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / 0")
        root.addWidget(self.progress_bar)

        log_label = QLabel("Лог обработки")
        log_label.setObjectName("sectionLabel")
        root.addWidget(log_label)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumBlockCount(2000)
        self.log_edit.setMinimumHeight(150)
        root.addWidget(self.log_edit, 2)

        self.add_button.clicked.connect(self._add_videos)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear_list)
        self.output_button.clicked.connect(self._choose_output_directory)
        self.start_button.clicked.connect(self._start_processing)
        self.cancel_button.clicked.connect(self._cancel_processing)

    @staticmethod
    def _make_seconds_input() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 999_999_999.0)
        spin.setDecimals(3)
        spin.setSingleStep(0.5)
        spin.setSuffix(" сек")
        spin.setMinimumWidth(130)
        return spin

    def _restore_settings(self) -> None:
        settings = self.settings_store.load()
        output = settings.get("output_directory", str(default_output_directory()))
        self.output_edit.setText(str(output))
        try:
            self.trim_start.setValue(max(0.0, float(settings.get("trim_start", 0))))
            self.trim_end.setValue(max(0.0, float(settings.get("trim_end", 0))))
        except (TypeError, ValueError):
            self.trim_start.setValue(0)
            self.trim_end.setValue(0)

    def _save_settings(self) -> None:
        self.settings_store.save(
            self.output_edit.text().strip(),
            self.trim_start.value(),
            self.trim_end.value(),
        )

    def _add_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Добавить видео",
            "",
            VIDEO_FILTER,
        )
        if not paths:
            return

        known_paths = {str(item.path.resolve()).casefold() for item in self.items}
        for raw_path in paths:
            path = Path(raw_path)
            normalized = str(path.resolve()).casefold()
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                self._append_log(f"Файл пропущен: неподдерживаемый формат — {path}")
                continue
            if normalized in known_paths:
                self._append_log(f"Файл уже в списке: {path}")
                continue
            item = VideoItem(path=path)
            self.items.append(item)
            known_paths.add(normalized)
            self._append_table_row(item)
            self._append_log(f"Добавлен файл: {path}")
        self._update_idle_progress()

    def _append_table_row(self, item: VideoItem) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        path_cell = QTableWidgetItem(str(item.path))
        path_cell.setToolTip(str(item.path))
        duration_cell = QTableWidgetItem("—")
        duration_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_cell = QTableWidgetItem(item.status)
        status_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, 0, path_cell)
        self.table.setItem(row, 1, duration_cell)
        self.table.setItem(row, 2, status_cell)

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            removed = self.items.pop(row)
            self.table.removeRow(row)
            self._append_log(f"Удалён из списка: {removed.path}")
        self._update_idle_progress()

    def _clear_list(self) -> None:
        if not self.items:
            return
        self.items.clear()
        self.table.setRowCount(0)
        self._append_log("Список файлов очищен.")
        self._update_idle_progress()

    def _choose_output_directory(self) -> None:
        initial = self.output_edit.text().strip() or str(default_output_directory())
        directory = QFileDialog.getExistingDirectory(self, "Выбрать папку вывода", initial)
        if directory:
            self.output_edit.setText(directory)
            self._save_settings()

    def _start_processing(self) -> None:
        if self.worker_thread is not None and self.worker_thread.isRunning():
            return
        if not self.items:
            QMessageBox.information(self, "CutFlow Batch", "Добавьте хотя бы один видеофайл.")
            return

        output_text = self.output_edit.text().strip()
        if not output_text:
            output_text = str(default_output_directory())
            self.output_edit.setText(output_text)
        output_directory = Path(output_text).expanduser()

        ffmpeg_path, ffprobe_path = find_ffmpeg_tools()
        if not ffmpeg_path:
            QMessageBox.critical(
                self,
                "FFmpeg не найден",
                "FFmpeg не найден. Установите FFmpeg или положите ffmpeg.exe рядом с программой.",
            )
            self._append_log("Ошибка: FFmpeg не найден.")
            return
        if not ffprobe_path:
            QMessageBox.critical(
                self,
                "FFprobe не найден",
                "FFprobe не найден. Установите FFmpeg полностью или положите ffprobe.exe рядом с программой.",
            )
            self._append_log("Ошибка: FFprobe не найден.")
            return

        try:
            output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Ошибка папки вывода", f"Не удалось создать папку:\n{exc}")
            return

        self._save_settings()
        for row, item in enumerate(self.items):
            item.status = "Ожидает"
            self.table.item(row, 2).setText(item.status)

        self.worker_thread = QThread(self)
        self.worker = VideoProcessor(
            items=list(self.items),
            output_directory=output_directory,
            trim_start=self.trim_start.value(),
            trim_end=self.trim_end.value(),
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.current_file.connect(self._set_current_file)
        self.worker.item_updated.connect(self._update_item)
        self.worker.progress.connect(self._update_progress)
        self.worker.finished.connect(self._processing_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._thread_finished)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)

        self._set_processing_state(True)
        self._append_log(
            f"Запущена очередь: файлов — {len(self.items)}, "
            f"начало — {self.trim_start.value():g} сек, конец — {self.trim_end.value():g} сек."
        )
        self.worker_thread.start()

    def _cancel_processing(self) -> None:
        if self.worker is None:
            return
        self.cancel_button.setEnabled(False)
        self.current_label.setText("Остановка текущей операции…")
        self._append_log("Запрошена отмена обработки…")
        self.worker.request_cancel()

    def _update_item(self, row: int, duration: object, status: str) -> None:
        if not (0 <= row < self.table.rowCount()):
            return
        if isinstance(duration, (int, float)):
            self.table.item(row, 1).setText(format_duration(float(duration)))
            self.items[row].duration = float(duration)
        self.table.item(row, 2).setText(status)
        self.items[row].status = status

    def _update_progress(self, completed: int, total: int) -> None:
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(completed)
        self.progress_bar.setFormat(f"{completed} / {total}")

    def _update_idle_progress(self) -> None:
        total = len(self.items)
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {total}")

    def _set_current_file(self, filename: str) -> None:
        self.current_label.setText(f"Текущий файл: {filename}")

    def _processing_finished(self, summary_object: object) -> None:
        summary = summary_object if isinstance(summary_object, ProcessingSummary) else ProcessingSummary()
        self._set_processing_state(False)
        heading = "Обработка отменена" if summary.cancelled else "Обработка завершена"
        result = (
            f"Успешно: {summary.successful}\n"
            f"Ошибок: {summary.errors}\n"
            f"Пропущено: {summary.skipped}"
        )
        self._append_log(f"{heading}. {result.replace(chr(10), '; ')}")
        if not self._close_after_finish:
            QMessageBox.information(self, heading, result)

    def _thread_finished(self) -> None:
        self.worker = None
        self.worker_thread = None
        if self._close_after_finish:
            QTimer.singleShot(0, self.close)

    def _set_processing_state(self, processing: bool) -> None:
        self.add_button.setEnabled(not processing)
        self.remove_button.setEnabled(not processing)
        self.clear_button.setEnabled(not processing)
        self.output_button.setEnabled(not processing)
        self.output_edit.setEnabled(not processing)
        self.trim_start.setEnabled(not processing)
        self.trim_end.setEnabled(not processing)
        self.start_button.setEnabled(not processing)
        self.cancel_button.setEnabled(processing)

    def _append_log(self, message: str) -> None:
        timestamp = QTime.currentTime().toString("HH:mm:ss")
        self.log_edit.appendPlainText(f"[{timestamp}] {message}")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_settings()
        if self.worker_thread is not None and self.worker_thread.isRunning():
            answer = QMessageBox.question(
                self,
                "Обработка выполняется",
                "Остановить обработку и закрыть приложение?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._close_after_finish = True
                self._cancel_processing()
            event.ignore()
            return
        event.accept()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #17191f;
                color: #e8eaf0;
                font-family: "Segoe UI";
                font-size: 10pt;
            }
            QLabel#title { color: #ffffff; }
            QLabel#subtitle { color: #8e96a8; font-size: 11pt; margin-bottom: 8px; }
            QLabel#sectionLabel { font-weight: 600; color: #cfd4df; }
            QFrame#settingsFrame {
                background-color: #20232b;
                border: 1px solid #303541;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #2b303b;
                border: 1px solid #3b4250;
                border-radius: 6px;
                padding: 8px 14px;
                min-height: 18px;
            }
            QPushButton:hover { background-color: #353c49; border-color: #596276; }
            QPushButton:pressed { background-color: #252a33; }
            QPushButton:disabled { color: #686f7d; background-color: #22252c; border-color: #2b2f38; }
            QPushButton#primaryButton { background-color: #4169e1; border-color: #5178e8; font-weight: 600; }
            QPushButton#primaryButton:hover { background-color: #5076e5; }
            QPushButton#dangerButton { background-color: #6e3039; border-color: #8d404b; }
            QLineEdit, QDoubleSpinBox, QPlainTextEdit, QTableWidget {
                background-color: #111319;
                border: 1px solid #343946;
                border-radius: 5px;
                selection-background-color: #3f64c9;
                selection-color: #ffffff;
            }
            QLineEdit, QDoubleSpinBox { padding: 7px; }
            QPlainTextEdit { padding: 7px; font-family: Consolas; font-size: 9pt; }
            QTableWidget { gridline-color: #292e38; alternate-background-color: #181b22; }
            QHeaderView::section {
                background-color: #272b34;
                color: #dce0e8;
                border: none;
                border-right: 1px solid #3a3f4b;
                padding: 8px;
                font-weight: 600;
            }
            QProgressBar {
                background-color: #111319;
                border: 1px solid #343946;
                border-radius: 6px;
                text-align: center;
                min-height: 20px;
            }
            QProgressBar::chunk { background-color: #4169e1; border-radius: 5px; }
            QScrollBar:vertical { background: #17191f; width: 12px; }
            QScrollBar::handle:vertical { background: #3b414e; border-radius: 5px; min-height: 24px; }
            """
        )


def format_duration(seconds: float) -> str:
    whole_seconds = int(seconds)
    hours, remainder = divmod(whole_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    milliseconds = int(round((seconds - whole_seconds) * 1000))
    if milliseconds == 1000:
        secs += 1
        milliseconds = 0
        if secs == 60:
            minutes += 1
            secs = 0
        if minutes == 60:
            hours += 1
            minutes = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def run_application() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("CutFlow Batch")
    app.setOrganizationName("CutFlow")
    window = MainWindow()
    window.show()
    return app.exec()
