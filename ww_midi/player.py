from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .model import Analysis, Config
from .wininput import WindowsInput


def build_actions(analysis: Analysis, pulse_ms: int) -> tuple[tuple[int, tuple[str, ...], tuple[str, ...]], ...]:
    """Return (time_us, keys_up, keys_down), truncating a pulse at a same-key retrigger."""
    down_at: dict[int, list[str]] = {}
    up_at: dict[int, list[str]] = {}
    next_time_by_key: dict[str, int] = {}
    for group in reversed(analysis.groups):
        for key in group.keys:
            nominal_up = group.time_us + pulse_ms * 1000
            release = min(nominal_up, next_time_by_key.get(key, nominal_up))
            up_at.setdefault(release, []).append(key)
            next_time_by_key[key] = group.time_us
        down_at.setdefault(group.time_us, []).extend(group.keys)
    return tuple(
        (timestamp, tuple(up_at.get(timestamp, ())), tuple(down_at.get(timestamp, ())))
        for timestamp in sorted(down_at.keys() | up_at.keys())
    )


class Player:
    def __init__(self, output: WindowsInput, status: Callable[[str], None]) -> None:
        self.output = output
        self.status = status
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def play(self, analysis: Analysis, config: Config) -> None:
        if self.playing:
            return
        if config.unmapped_note == "error" and analysis.unmapped:
            raise ValueError("Unmapped notes must be resolved before playback")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(analysis, config), name="midi-player", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.output.release_all()

    def _interruptible_wait(self, seconds: float) -> bool:
        return self._stop.wait(max(0.0, seconds))

    def _wait_until(self, deadline_ns: int) -> bool:
        while not self._stop.is_set():
            remaining_ns = deadline_ns - time.perf_counter_ns()
            if remaining_ns <= 0:
                return False
            if remaining_ns > 2_000_000:
                self._stop.wait((remaining_ns - 1_000_000) / 1_000_000_000)
            else:
                time.sleep(0)
        return True

    def _run(self, analysis: Analysis, config: Config) -> None:
        max_late_us = 0
        try:
            self.status(f"Starting in {config.start_delay_ms / 1000:g} seconds...")
            if self._interruptible_wait(config.start_delay_ms / 1000):
                return
            if config.require_target_window:
                title = self.output.foreground_title()
                if config.target_window_title.lower() not in title.lower():
                    self.status(f"Stopped: foreground window is '{title or '(untitled)'}'")
                    return

            actions = build_actions(analysis, config.pulse_ms)
            scans = {key: self.output.scan_code(key) for group in analysis.groups for key in group.keys}
            start_ns = time.perf_counter_ns()
            self.status("Playing")
            for time_us, keys_up, keys_down in actions:
                deadline = start_ns + time_us * 1000
                if self._wait_until(deadline):
                    return
                late_us = max(0, (time.perf_counter_ns() - deadline) // 1000)
                max_late_us = max(max_late_us, late_us)
                # Release first when a repeated note ends and restarts at the same instant.
                self.output.key_up([scans[key] for key in keys_up])
                self.output.key_down([scans[key] for key in keys_down])
            self.status(f"Finished (maximum scheduling delay: {max_late_us / 1000:.2f} ms)")
            logging.info("Playback finished; maximum delay %.3f ms", max_late_us / 1000)
        except Exception as exc:
            logging.exception("Playback failed")
            self.status(f"Playback error: {exc}")
        finally:
            self.output.release_all()
