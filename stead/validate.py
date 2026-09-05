"""Bake-time check of a STEAD record against its dump.

A record is kept only if: S exists in D, D shows A on S at T, A != E, and T
lies inside the dump. Anything else is dropped to `stead: null` with the
reason; a bad line never poisons a case.
"""

from __future__ import annotations

from pathlib import Path

from .fail import Stead
from .wave import end_time, open_dump, value_at


def validate_stead(s: Stead, dump: Path | str) -> tuple[bool, str]:
    if s.expected == s.actual:
        return False, f"expected == actual (0x{s.actual:x})"
    wave = open_dump(dump)
    try:
        got = value_at(wave, s.signal, s.time)
    except KeyError:
        return False, f"signal {s.signal} not in dump {dump}"
    if s.time > end_time(wave):
        return False, f"time {s.time} beyond end of dump"
    if got != s.actual:
        shown = "none" if got is None else f"0x{got:x}"
        return False, f"dump@t shows {shown}, record says actual=0x{s.actual:x}"
    return True, "ok"
