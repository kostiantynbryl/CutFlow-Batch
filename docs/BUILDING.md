# Сборка CutFlow Batch для Windows

## Требования

Для сборки нужны:

- Windows 10/11;
- Python 3.11+;
- доступ к `pip`;
- зависимости из `requirements.txt`.

Проверка Python:

```bat
python --version
python -m pip --version
```

## Автоматическая сборка

В корне проекта находится `build_exe.bat`.

Запустите его из Проводника или из терминала:

```bat
build_exe.bat
```

Скрипт выполняет следующие действия:

```text
1. python -m pip install --upgrade pip
2. python -m pip install -r requirements.txt
3. python -m PyInstaller --noconfirm --clean --onefile --windowed --name CutFlowBatch main.py
4. копирование ffmpeg.exe и ffprobe.exe в dist, если они есть в корне проекта
```

Готовый файл:

```text
dist\CutFlowBatch.exe
```

## FFmpeg рядом с EXE

Сам `CutFlowBatch.exe` не содержит FFmpeg внутри.

Для переносимой папки рекомендуется получить такую структуру:

```text
dist/
├── CutFlowBatch.exe
├── ffmpeg.exe
└── ffprobe.exe
```

Если `ffmpeg.exe` и `ffprobe.exe` находятся в корне проекта до запуска `build_exe.bat`, скрипт автоматически копирует их в `dist`.

Второй вариант — не класть FFmpeg рядом с приложением, а добавить его каталог `bin` в системный `PATH`.

## Ручная сборка

Можно выполнить те же действия вручную:

```bat
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CutFlowBatch main.py
```

## Файл CutFlowBatch.spec

В репозитории также есть `CutFlowBatch.spec`. Он описывает оконную PyInstaller-сборку с именем `CutFlowBatch`.

Его можно использовать отдельно:

```bat
python -m PyInstaller --noconfirm --clean CutFlowBatch.spec
```

Текущий `build_exe.bat` использует параметры командной строки PyInstaller напрямую и не вызывает `.spec` автоматически.

## Что не нужно коммитить

`.gitignore` исключает:

- `build/`;
- `dist/`;
- `__pycache__/`;
- локальные `ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`;
- `cutflow_settings.json`;
- runtime-логи и временные файлы.

Поэтому бинарные сборки лучше публиковать через **GitHub Releases**, а не хранить в основной истории Git.

## Рекомендуемый пакет релиза

Для пользователя без Python можно подготовить ZIP:

```text
CutFlowBatch-Windows-x64/
├── CutFlowBatch.exe
├── ffmpeg.exe
├── ffprobe.exe
└── README.txt
```

Перед публикацией проверьте лицензии и условия распространения конкретной сборки FFmpeg, которую включаете в архив.

## Проверка готовой сборки

После сборки рекомендуется проверить:

1. запуск `CutFlowBatch.exe` без консольного окна;
2. обнаружение `ffmpeg.exe` и `ffprobe.exe`;
3. добавление каждого поддерживаемого расширения;
4. обрезку только начала;
5. обрезку только конца;
6. обрезку начала и конца одновременно;
7. создание `_cut_1.mp4`, если имя занято;
8. отмену обработки;
9. сохранение настроек после перезапуска.
