"""Cross-platform advisory file lock used for per-account serialization."""

from __future__ import annotations

import os
import time
from pathlib import Path

from .errors import LockTimeout

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None  # type: ignore[assignment]


class FileLock:
    def __init__(self, path: Path, timeout_s: float = 30.0) -> None:
        self.path = Path(path)
        self.timeout_s = timeout_s
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + max(0.0, self.timeout_s)
        while True:
            try:
                self._try_lock(fd)
                self._fd = fd
                return
            except (BlockingIOError, OSError) as exc:
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise LockTimeout(f"获取锁超时: {self.path}") from exc
                time.sleep(0.05)

    def _try_lock(self, fd: int) -> None:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        if msvcrt is not None:  # pragma: no cover - Windows
            os.lseek(fd, 0, os.SEEK_SET)
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        raise LockTimeout("当前平台不支持文件锁")

    def release(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - Windows
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
