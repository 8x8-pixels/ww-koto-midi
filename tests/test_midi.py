from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ww_midi.midi import MidiError, load_midi
from ww_midi.model import analyze, load_config, quantize_note
from ww_midi.model import Analysis, PlayGroup
from ww_midi.player import build_actions


def vlq(value: int) -> bytes:
    result = [value & 0x7F]
    value >>= 7
    while value:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(result))


def midi_file(tracks: list[bytes], format_type: int = 1, ppq: int = 480) -> bytes:
    header = format_type.to_bytes(2, "big") + len(tracks).to_bytes(2, "big") + ppq.to_bytes(2, "big")
    chunks = b"".join(b"MTrk" + len(track).to_bytes(4, "big") + track for track in tracks)
    return b"MThd" + len(header).to_bytes(4, "big") + header + chunks


class MidiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        config = {
            "pulse_ms": 20, "start_delay_ms": 0, "unmapped_note": "error",
            "keymap": {"60": "A", "64": "D", "67": "G"},
        }
        self.config_path = self.directory / "keymap.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_midi(self, content: bytes) -> Path:
        path = self.directory / "test.mid"
        path.write_bytes(content)
        return path

    def test_running_status_velocity_zero_and_tempo(self) -> None:
        track = (
            b"\x00\xFF\x51\x03\x07\xA1\x20"  # 500000 us/qn
            b"\x00\x90\x3C\x64"                # C4 on
            + vlq(480) + b"\x40\x64"             # E4 on, running status
            + vlq(480) + b"\x43\x00"             # G4 velocity zero
            b"\x00\xFF\x2F\x00"
        )
        song = load_midi(self.write_midi(midi_file([track], format_type=0)))
        result = analyze(song, load_config(self.config_path))
        self.assertEqual([note.note for note in song.notes], [60, 64])
        self.assertEqual([group.time_us for group in result.groups], [0, 500_000])

    def test_fixed_bpm_ignores_tempo_events(self) -> None:
        track = (
            b"\x00\xFF\x51\x03\x0F\x42\x40"  # 60 BPM in the file
            b"\x00\x90\x3C\x64"
            + vlq(480) + b"\x40\x64"
            + b"\x00\xFF\x2F\x00"
        )
        song = load_midi(self.write_midi(midi_file([track], format_type=0)))
        result = analyze(song, load_config(self.config_path), fixed_bpm=120)
        self.assertEqual([group.time_us for group in result.groups], [0, 500_000])

    def test_fixed_bpm_is_validated(self) -> None:
        song = load_midi(self.write_midi(midi_file([b"\x00\xFF\x2F\x00"], format_type=0)))
        with self.assertRaisesRegex(ValueError, "BPM"):
            analyze(song, load_config(self.config_path), fixed_bpm=0)

    def test_type_one_tracks_are_merged_and_chords_grouped(self) -> None:
        tempo_track = b"\x00\xFF\x51\x03\x0F\x42\x40\x00\xFF\x2F\x00"
        notes_a = b"\x00\x90\x3C\x40\x00\x90\x40\x40\x00\xFF\x2F\x00"
        notes_b = b"\x00\x90\x43\x40\x00\xFF\x2F\x00"
        song = load_midi(self.write_midi(midi_file([tempo_track, notes_a, notes_b])))
        result = analyze(song, load_config(self.config_path))
        self.assertEqual(result.note_count, 3)
        self.assertEqual(result.max_polyphony, 3)
        self.assertEqual(set(result.groups[0].keys), {"A", "D", "G"})

    def test_unmapped_notes_are_counted(self) -> None:
        track = b"\x00\x90\x3D\x40\x00\x90\x3D\x40\x00\xFF\x2F\x00"
        result = analyze(
            load_midi(self.write_midi(midi_file([track], format_type=0))),
            load_config(self.config_path),
        )
        self.assertEqual(result.unmapped, {61: 2})

    def test_smpte_is_rejected(self) -> None:
        data = midi_file([b"\x00\xFF\x2F\x00"], format_type=0, ppq=0xE728)
        with self.assertRaisesRegex(MidiError, "SMPTE"):
            load_midi(self.write_midi(data))

    def test_key_up_does_not_delay_next_note_and_retrigger_is_clean(self) -> None:
        analysis = Analysis(
            groups=(PlayGroup(0, ("A",)), PlayGroup(10_000, ("A", "D"))),
            note_count=3, duration_us=10_000, max_polyphony=2, unmapped={},
        )
        self.assertEqual(
            build_actions(analysis, pulse_ms=20),
            (
                (0, (), ("A",)),
                (10_000, ("A",), ("A", "D")),
                (30_000, ("A", "D"), ()),
            ),
        )

    def test_quantize_folds_octaves_and_moves_black_keys(self) -> None:
        keymap = {48: "Z", 50: "X", 52: "C", 53: "V", 55: "B", 57: "N", 59: "M",
                  60: "A", 62: "S", 64: "D", 65: "F", 67: "G", 69: "H", 71: "J",
                  72: "Q", 74: "W", 76: "E", 77: "R", 79: "T", 81: "Y", 83: "U"}
        self.assertEqual(quantize_note(38, keymap), 50)  # D2 -> D3
        self.assertEqual(quantize_note(47, keymap), 59)  # B2 -> B3
        self.assertEqual(quantize_note(66, keymap), 65)  # F#4 -> F4 (lower tie)


if __name__ == "__main__":
    unittest.main()
