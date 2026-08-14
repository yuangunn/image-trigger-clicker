"""로그 출력.

[HH:MM:SS] 타임스탬프를 붙이고 항상 즉시 flush 한다.
장시간 무인 실행이 전제라, 버퍼에 갇혀 안 보이는 로그는 없느니만 못하다.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import TextIO

__all__ = ["close_log_file", "log", "open_log_file", "warn"]

_log_file: TextIO | None = None


def open_log_file(path: Path) -> None:
    """로그를 파일에도 남긴다. 이어쓰기(append)."""
    global _log_file
    close_log_file()
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = path.open("a", encoding="utf-8")


def close_log_file() -> None:
    global _log_file
    if _log_file is not None:
        _log_file.close()
        _log_file = None


def _emit(message: str, stream: TextIO) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {message}"
    print(line, file=stream, flush=True)
    if _log_file is not None:
        _log_file.write(line + "\n")
        _log_file.flush()


def log(message: str) -> None:
    """[HH:MM:SS] 접두사를 붙여 표준 출력(+ 로그 파일)에 쓴다."""
    _emit(message, sys.stdout)


def warn(message: str) -> None:
    """경고. 루프를 멈추지는 않는다."""
    _emit(f"[경고] {message}", sys.stdout)


def error(message: str) -> None:
    """치명적 오류. 표준 에러로 낸다 (파이프로 걸러낼 수 있게)."""
    _emit(f"[오류] {message}", sys.stderr)
