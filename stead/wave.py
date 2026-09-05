"""Read one signal out of a dump.

The engine is pywellen (wellen, Surfer's waveform core); it reads VCD and FST
directly. This module owns only the two questions bake asks of a dump:

    value_at(dump, signal, t)   -> int | None   (None: X/Z, or before the first change)
    end_time(dump)              -> int          (last time step in the dump)

Never use `var[t]`: it raises IndexError before the first change. `signal.value_at`
returns None there.
"""

from __future__ import annotations

from pathlib import Path

import pywellen


def open_dump(dump: Path | str) -> pywellen.Waveform:
    return pywellen.Waveform(str(dump))


def value_at(wave: pywellen.Waveform, signal: str, t: int) -> int | None:
    """Value `signal` (full dotted path) holds at time t. KeyError if the signal is not in the dump."""
    v = wave[signal].signal.value_at(t)
    return v if isinstance(v, int) else None  # X/Z come back as strings


def end_time(wave: pywellen.Waveform) -> int:
    """Last time step in the dump. Streams every signal's change times once; bake pays this per case."""
    steps: list[int] = []
    wave.stream_time_steps(lambda t, *_: steps.append(t), list(wave.all_vars()))
    return steps[-1] if steps else 0
