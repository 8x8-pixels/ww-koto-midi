from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


if os.name == "nt":
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG), ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1


class WindowsInput:
    def __init__(self) -> None:
        if os.name != "nt":
            raise OSError("Keyboard output is only available on Windows")
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        self._user32.SendInput.restype = wintypes.UINT
        expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
        if ctypes.sizeof(INPUT) != expected_size:
            raise RuntimeError(
                f"Invalid Win32 INPUT structure size: {ctypes.sizeof(INPUT)} (expected {expected_size})"
            )
        self._pressed: set[int] = set()

    def scan_code(self, key: str) -> int:
        virtual_key = ord(key.upper())
        scan = self._user32.MapVirtualKeyW(virtual_key, 0)
        if scan == 0:
            raise ValueError(f"Cannot map key {key!r} to a scan code")
        return scan

    def _send(self, scans: list[int], key_up: bool) -> None:
        if not scans:
            return
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
        array_type = INPUT * len(scans)
        inputs = array_type(*[
            INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(0, scan, flags, 0, 0)))
            for scan in scans
        ])
        sent = self._user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT))
        if sent != len(inputs):
            raise ctypes.WinError(ctypes.get_last_error())
        if key_up:
            self._pressed.difference_update(scans)
        else:
            self._pressed.update(scans)

    def key_down(self, scans: list[int]) -> None:
        self._send(scans, False)

    def key_up(self, scans: list[int]) -> None:
        self._send(scans, True)

    def release_all(self) -> None:
        if self._pressed:
            self._send(list(self._pressed), True)

    def foreground_title(self) -> str:
        hwnd = self._user32.GetForegroundWindow()
        length = self._user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value

    def key_pressed(self, virtual_key: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(virtual_key) & 0x8000)

    def is_elevated(self) -> bool:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
