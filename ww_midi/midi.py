from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class MidiError(ValueError):
    pass


@dataclass(frozen=True)
class RawNote:
    tick: int
    note: int


@dataclass(frozen=True)
class Tempo:
    tick: int
    microseconds_per_quarter: int


@dataclass(frozen=True)
class MidiSong:
    format: int
    ppq: int
    notes: tuple[RawNote, ...]
    tempos: tuple[Tempo, ...]


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise MidiError("Unexpected end of MIDI file")
    return data


def _u16(data: bytes) -> int:
    return int.from_bytes(data, "big")


def _u32(data: bytes) -> int:
    return int.from_bytes(data, "big")


def _vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise MidiError("Truncated variable-length quantity")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    raise MidiError("Variable-length quantity exceeds 4 bytes")


def _parse_track(data: bytes) -> tuple[list[RawNote], list[Tempo]]:
    notes: list[RawNote] = []
    tempos: list[Tempo] = []
    offset = 0
    tick = 0
    running_status: int | None = None

    while offset < len(data):
        delta, offset = _vlq(data, offset)
        tick += delta
        if offset >= len(data):
            raise MidiError("Track ends before event status")

        byte = data[offset]
        if byte & 0x80:
            status = byte
            offset += 1
            if status < 0xF0:
                running_status = status
        elif running_status is not None:
            status = running_status
        else:
            raise MidiError("Data byte encountered without running status")

        if status == 0xFF:
            running_status = None
            if offset >= len(data):
                raise MidiError("Truncated meta event")
            meta_type = data[offset]
            offset += 1
            length, offset = _vlq(data, offset)
            if offset + length > len(data):
                raise MidiError("Truncated meta event payload")
            payload = data[offset : offset + length]
            offset += length
            if meta_type == 0x51:
                if length != 3:
                    raise MidiError("Set Tempo event must contain 3 bytes")
                tempos.append(Tempo(tick, int.from_bytes(payload, "big")))
            if meta_type == 0x2F:
                break
            continue

        if status in (0xF0, 0xF7):
            running_status = None
            length, offset = _vlq(data, offset)
            if offset + length > len(data):
                raise MidiError("Truncated SysEx payload")
            offset += length
            continue

        kind = status & 0xF0
        data_length = 1 if kind in (0xC0, 0xD0) else 2
        if kind < 0x80 or kind > 0xE0 or offset + data_length > len(data):
            raise MidiError(f"Invalid or truncated MIDI event 0x{status:02X}")
        first = data[offset]
        second = data[offset + 1] if data_length == 2 else 0
        offset += data_length
        if kind == 0x90 and second > 0:
            notes.append(RawNote(tick, first))

    return notes, tempos


def load_midi(path: str | Path) -> MidiSong:
    with Path(path).open("rb") as stream:
        if _read_exact(stream, 4) != b"MThd":
            raise MidiError("Missing MThd header")
        header_length = _u32(_read_exact(stream, 4))
        header = _read_exact(stream, header_length)
        if header_length < 6:
            raise MidiError("MIDI header is too short")
        format_type, track_count, division = _u16(header[:2]), _u16(header[2:4]), _u16(header[4:6])
        if format_type not in (0, 1):
            raise MidiError(f"SMF Type {format_type} is not supported")
        if division & 0x8000:
            raise MidiError("SMPTE time division is not supported")
        if division == 0:
            raise MidiError("PPQ must be greater than zero")

        notes: list[RawNote] = []
        tempos: list[Tempo] = []
        for _ in range(track_count):
            if _read_exact(stream, 4) != b"MTrk":
                raise MidiError("Missing MTrk chunk")
            track = _read_exact(stream, _u32(_read_exact(stream, 4)))
            track_notes, track_tempos = _parse_track(track)
            notes.extend(track_notes)
            tempos.extend(track_tempos)

    notes.sort(key=lambda event: event.tick)
    tempos.sort(key=lambda event: event.tick)
    return MidiSong(format_type, division, tuple(notes), tuple(tempos))
