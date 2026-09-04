from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path

from .midi import MidiSong


@dataclass(frozen=True)
class Config:
    pulse_ms: int
    start_delay_ms: int
    unmapped_note: str
    require_target_window: bool
    target_window_title: str
    keymap: dict[int, str]


@dataclass(frozen=True)
class PlayGroup:
    time_us: int
    keys: tuple[str, ...]


@dataclass(frozen=True)
class Analysis:
    groups: tuple[PlayGroup, ...]
    note_count: int
    duration_us: int
    max_polyphony: int
    unmapped: dict[int, int]


def load_config(path: str | Path) -> Config:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    mode = raw.get("unmapped_note", "error")
    if mode not in ("error", "ignore", "quantize"):
        raise ValueError("unmapped_note must be 'error', 'ignore', or 'quantize'")
    pulse = int(raw.get("pulse_ms", 20))
    delay = int(raw.get("start_delay_ms", 3000))
    if not 1 <= pulse <= 1000 or not 0 <= delay <= 60000:
        raise ValueError("pulse_ms or start_delay_ms is out of range")
    keymap = {int(note): str(key).upper() for note, key in raw["keymap"].items()}
    if any(len(key) != 1 or not key.isalpha() for key in keymap.values()):
        raise ValueError("Initial keymap supports single alphabetic keys only")
    return Config(
        pulse, delay, mode, bool(raw.get("require_target_window", True)),
        str(raw.get("target_window_title", "鳴潮")), keymap,
    )


def analyze(song: MidiSong, config: Config, fixed_bpm: float | None = None) -> Analysis:
    if fixed_bpm is not None and not 1 <= fixed_bpm <= 999:
        raise ValueError("BPM must be between 1 and 999")
    tempo_events = [] if fixed_bpm is not None else sorted(song.tempos, key=lambda event: event.tick)
    current_tick = 0
    current_us = 0
    tempo = round(60_000_000 / fixed_bpm) if fixed_bpm is not None else 500_000
    tempo_index = 0
    groups: list[PlayGroup] = []
    unmapped: Counter[int] = Counter()

    note_index = 0
    while note_index < len(song.notes):
        tick = song.notes[note_index].tick
        while tempo_index < len(tempo_events) and tempo_events[tempo_index].tick <= tick:
            event = tempo_events[tempo_index]
            current_us += (event.tick - current_tick) * tempo // song.ppq
            current_tick = event.tick
            tempo = event.microseconds_per_quarter
            tempo_index += 1
        event_us = current_us + (tick - current_tick) * tempo // song.ppq
        keys: list[str] = []
        while note_index < len(song.notes) and song.notes[note_index].tick == tick:
            note = song.notes[note_index].note
            key = config.keymap.get(note)
            if key is None and config.unmapped_note == "quantize":
                mapped_note = quantize_note(note, config.keymap)
                key = config.keymap[mapped_note]
            if key is None:
                unmapped[note] += 1
            elif key not in keys:
                keys.append(key)
            note_index += 1
        if keys:
            groups.append(PlayGroup(event_us, tuple(keys)))

    return Analysis(
        tuple(groups), len(song.notes), groups[-1].time_us if groups else 0,
        max((len(group.keys) for group in groups), default=0), dict(sorted(unmapped.items())),
    )


def quantize_note(note: int, keymap: dict[int, str]) -> int:
    """Fold by octaves where possible, then choose the nearest playable note."""
    if not keymap:
        raise ValueError("keymap must not be empty")
    candidates = sorted(keymap)
    folded = note
    while folded < candidates[0]:
        folded += 12
    while folded > candidates[-1]:
        folded -= 12
    # On an equal-distance tie, prefer the lower pitch for deterministic harmony.
    return min(candidates, key=lambda candidate: (abs(candidate - folded), candidate))
