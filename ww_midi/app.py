from __future__ import annotations

import logging
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .midi import MidiError, MidiSong, load_midi
from .model import Analysis, Config, analyze, load_config
from .player import Player
from .wininput import WindowsInput


class App:
    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root = root
        self.config_path = config_path
        self.config: Config | None = None
        self.song: MidiSong | None = None
        self.analysis: Analysis | None = None
        self.file_path: Path | None = None
        self.output = WindowsInput()
        self.player = Player(self.output, self._set_status_threadsafe)
        self._hotkey_stop = threading.Event()

        privilege = "Administrator" if self.output.is_elevated() else "Standard user"
        root.title(f"Wuthering Waves MIDI Player [{privilege}]")
        root.geometry("620x390")
        root.minsize(560, 350)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build_ui()
        self.reload_config()
        threading.Thread(target=self._hotkey_loop, name="hotkeys", daemon=True).start()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        self.path_var = tk.StringVar(value="No MIDI file selected")
        ttk.Label(frame, textvariable=self.path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Open...", command=self.open_file).grid(row=0, column=1)
        ttk.Separator(frame).grid(row=1, column=0, columnspan=2, sticky="ew", pady=14)
        self.info_var = tk.StringVar(value="Open a Standard MIDI File to validate it.")
        ttk.Label(frame, textvariable=self.info_var, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="nw"
        )
        self.unmapped_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.unmapped_var, foreground="#a22", justify="left").grid(
            row=3, column=0, columnspan=2, sticky="nw", pady=(10, 0)
        )
        frame.rowconfigure(4, weight=1)
        controls = ttk.Frame(frame)
        controls.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.play_button = ttk.Button(controls, text="Play (F6)", command=self.play, state="disabled")
        self.play_button.pack(side="left")
        ttk.Button(controls, text="Stop (F7 / Esc)", command=self.stop).pack(side="left", padx=8)
        ttk.Button(controls, text="Reload config", command=self.reload_config).pack(side="left")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var, relief="sunken", padding=6).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=(14, 0)
        )

    def reload_config(self) -> None:
        try:
            self.config = load_config(self.config_path)
            self._reanalyze()
            self.status_var.set(f"Loaded {self.config_path.name}")
        except Exception as exc:
            self.config = None
            self.play_button.configure(state="disabled")
            messagebox.showerror("Configuration error", str(exc))

    def open_file(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")])
        if not selected:
            return
        try:
            self.file_path = Path(selected)
            self.song = load_midi(self.file_path)
            self.path_var.set(str(self.file_path))
            self._reanalyze()
        except (OSError, MidiError) as exc:
            self.song = None
            self.analysis = None
            self.play_button.configure(state="disabled")
            messagebox.showerror("MIDI error", str(exc))

    def _reanalyze(self) -> None:
        if self.song is None or self.config is None:
            return
        self.analysis = analyze(self.song, self.config)
        a = self.analysis
        self.info_var.set(
            f"SMF Type: {self.song.format}\nPPQ: {self.song.ppq}\nDuration: {a.duration_us / 1_000_000:.3f} sec\n"
            f"Note On events: {a.note_count}\nMax polyphony: {a.max_polyphony}\nTempo events: {len(self.song.tempos)}"
        )
        if a.unmapped:
            details = "\n".join(f"  MIDI {note}: {count} events" for note, count in a.unmapped.items())
            label = "Quantized source notes" if self.config.unmapped_note == "quantize" else "Unmapped notes"
            self.unmapped_var.set(f"{label}:\n{details}")
        else:
            self.unmapped_var.set("Unmapped notes: 0")
        blocked = bool(a.unmapped and self.config.unmapped_note == "error")
        self.play_button.configure(state="disabled" if blocked else "normal")
        self.status_var.set("Validation failed" if blocked else "Validated")

    def play(self) -> None:
        if self.analysis is None or self.config is None:
            return
        try:
            self.player.play(self.analysis, self.config)
        except ValueError as exc:
            messagebox.showerror("Cannot play", str(exc))

    def stop(self) -> None:
        self.player.stop()
        self.status_var.set("Stopped")

    def _set_status_threadsafe(self, message: str) -> None:
        self.root.after(0, self.status_var.set, message)

    def _hotkey_loop(self) -> None:
        # Edge-triggered polling keeps the controls global without a separate message window.
        keys = {0x75: self.play, 0x76: self.stop, 0x1B: self.stop}  # F6, F7, Escape
        previous = {key: False for key in keys}
        while not self._hotkey_stop.wait(0.03):
            for key, callback in keys.items():
                pressed = self.output.key_pressed(key)
                if pressed and not previous[key]:
                    self.root.after(0, callback)
                previous[key] = pressed

    def close(self) -> None:
        self._hotkey_stop.set()
        self.player.stop()
        self.root.destroy()


def main() -> int:
    base = Path(__file__).resolve().parent.parent
    logging.basicConfig(
        filename=base / "wuthering-midi-player.log", level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    root = tk.Tk()
    app = App(root, base / "keymap.json")
    if len(sys.argv) > 1:
        try:
            app.file_path = Path(sys.argv[1]).resolve()
            app.song = load_midi(app.file_path)
            app.path_var.set(str(app.file_path))
            app._reanalyze()
        except Exception as exc:
            messagebox.showerror("MIDI error", str(exc))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
