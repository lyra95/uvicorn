from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from socket import socket
from types import FrameType

from uvicorn._ansi import style
from uvicorn._subprocess import get_subprocess
from uvicorn.config import Config

HANDLED_SIGNALS: tuple[signal.Signals, ...] = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)
if sys.platform == "win32":  # pragma: py-not-win32
    # Windows delivers CTRL_BREAK_EVENT as SIGBREAK. The reloader shares its
    # console with the child, so it has to handle the event it sends.
    HANDLED_SIGNALS += (signal.SIGBREAK,)

logger = logging.getLogger("uvicorn.error")


class BaseReload:
    def __init__(
        self,
        config: Config,
        target: Callable[[list[socket] | None], None],
        sockets: list[socket],
    ) -> None:
        self.config = config
        self.target = target
        self.sockets = sockets
        self.should_exit = threading.Event()
        self.pid = os.getpid()
        self.reloader_name: str | None = None

    def signal_handler(self, sig: int, frame: FrameType | None) -> None:  # pragma: full coverage
        """
        A signal handler that is registered with the parent process.
        """
        if sys.platform == "win32" and sig == signal.SIGBREAK:
            # Sent by us to the child; the console delivers it here as well.
            return
        self.should_exit.set()

    def run(self) -> None:
        self.startup()
        for changes in self:
            if changes:
                logger.warning(
                    "%s detected changes in %s. Reloading...",
                    self.reloader_name,
                    ", ".join(map(_display_path, changes)),
                )
                self.restart()

        self.shutdown()

    def pause(self) -> None:
        if self.should_exit.wait(self.config.reload_delay):
            raise StopIteration()

    def __iter__(self) -> Iterator[list[Path] | None]:
        return self

    def __next__(self) -> list[Path] | None:
        return self.should_restart()

    def startup(self) -> None:
        message = f"Started reloader process [{self.pid}] using {self.reloader_name}"
        color_message = "Started reloader process [{}] using {}".format(
            style(str(self.pid), fg="cyan", bold=True),
            style(str(self.reloader_name), fg="cyan", bold=True),
        )
        logger.info(message, extra={"color_message": color_message})

        for sig in HANDLED_SIGNALS:
            signal.signal(sig, self.signal_handler)

        self.process = get_subprocess(config=self.config, target=self.target, sockets=self.sockets)
        self.process.start()

    def _terminate_process(self) -> None:
        """Ask the child process to shut down.

        Windows has no SIGTERM, so send CTRL_BREAK_EVENT and let the child turn
        it into SIGTERM, the same way `Multiprocess` stops its workers.
        """
        if sys.platform == "win32":  # pragma: py-not-win32
            assert self.process.pid is not None
            os.kill(self.process.pid, signal.CTRL_BREAK_EVENT)
        else:  # pragma: py-win32
            self.process.terminate()

    def restart(self) -> None:
        self._terminate_process()
        self.process.join()

        self.process = get_subprocess(config=self.config, target=self.target, sockets=self.sockets)
        self.process.start()

    def shutdown(self) -> None:
        self.should_exit.set()
        self._terminate_process()
        self.process.join()

        for sock in self.sockets:
            sock.close()

        message = f"Stopping reloader process [{str(self.pid)}]"
        color_message = "Stopping reloader process [{}]".format(style(str(self.pid), fg="cyan", bold=True))
        logger.info(message, extra={"color_message": color_message})

    def should_restart(self) -> list[Path] | None:
        raise NotImplementedError("Reload strategies should override should_restart()")


def _display_path(path: Path) -> str:
    try:
        return f"'{path.relative_to(Path.cwd())}'"
    except ValueError:
        return f"'{path}'"
