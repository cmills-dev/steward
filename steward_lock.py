"""Cross-process locks for queue updates and launch admission on Windows and POSIX."""
from __future__ import annotations

import contextlib
import errno
import os
import time
from pathlib import Path


@contextlib.contextmanager
def file_lock(path: Path, blocking=True):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+b") as f:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    if path.stat().st_size == 0:
                        f.write(b"0")
                        f.flush()
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if not blocking:
                    yield None
                    return
                time.sleep(0.05)
        try:
            yield f
        finally:
            unlock(f)


def unlock(f):
    if os.name == "nt":
        import msvcrt
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)
