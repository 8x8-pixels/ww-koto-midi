from __future__ import annotations

import argparse
from pathlib import Path

from ww_midi.midi import load_midi
from ww_midi.model import analyze, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a MIDI file without sending keyboard input")
    parser.add_argument("midi", type=Path)
    parser.add_argument("--keymap", type=Path, default=Path("keymap.json"))
    args = parser.parse_args()
    song = load_midi(args.midi)
    result = analyze(song, load_config(args.keymap))
    print(f"SMF Type: {song.format}")
    print(f"PPQ: {song.ppq}")
    print(f"Duration: {result.duration_us / 1_000_000:.3f} sec")
    print(f"Note On events: {result.note_count}")
    print(f"Max polyphony: {result.max_polyphony}")
    print(f"Tempo events: {len(song.tempos)}")
    if result.unmapped:
        label = "Quantized source notes" if load_config(args.keymap).unmapped_note == "quantize" else "Unmapped notes"
        print(f"{label}:")
        for note, count in result.unmapped.items():
            print(f"  MIDI {note}: {count} events")
        if load_config(args.keymap).unmapped_note == "error":
            return 2
    print("Unmapped notes: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
