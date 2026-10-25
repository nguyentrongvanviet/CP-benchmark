"""Process-scoped collector ownership; a second process must never reset live jobs."""

import os
from pathlib import Path


class CollectorBusy(RuntimeError):
    pass


class CollectorLock:
    def __init__(self, root):
        self.path = Path(root) / "collector.lock"
        self.file = None

    def acquire(self):
        file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                file.seek(0)
                if not file.read(1):
                    file.write(b"0")
                    file.flush()
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            file.close()
            raise CollectorBusy(
                "Another CPBench process owns this data directory. Use its API, or stop it before starting another collector."
            ) from exc
        self.file = file
        return self

    def close(self):
        if self.file is not None:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.close()
