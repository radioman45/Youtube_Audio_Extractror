from __future__ import annotations

import threading


class PauseController:
    def __init__(self) -> None:
        self._resume_event = threading.Event()
        self._resume_event.set()

    def pause(self) -> None:
        self._resume_event.clear()

    def resume(self) -> None:
        self._resume_event.set()

    def is_paused(self) -> bool:
        return not self._resume_event.is_set()

    def wait_until_resumed(self, timeout: float | None = None) -> bool:
        return self._resume_event.wait(timeout)
