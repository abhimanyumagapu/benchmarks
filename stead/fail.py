"""The STEAD fail record and the log line that carries it.

    FAIL  test=<name>  signal=<S>  time=<T>  expected=<E>  actual=<A>  dump=<D>

All four of S, T, E, A must be present; a FAIL line missing any of them is
not a STEAD record (partial knowledge belongs in a NOTE line).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FAIL = re.compile(
    r"^\s*FAIL\s+test=(?P<test>\S+)\s+signal=(?P<signal>\S+)\s+time=(?P<time>\d+)\s+"
    r"expected=0x(?P<expected>[0-9a-fA-F]+)\s+actual=0x(?P<actual>[0-9a-fA-F]+)"
    r"(?:\s+dump=(?P<dump>\S+))?\s*$"
)


@dataclass(frozen=True)
class Stead:
    test: str
    signal: str
    time: int
    expected: int
    actual: int
    dump: str | None = None

    def to_dict(self) -> dict:
        return {
            "test": self.test,
            "signal": self.signal,
            "time": self.time,
            "expected": f"0x{self.expected:08x}",
            "actual": f"0x{self.actual:08x}",
            "dump": self.dump,
        }


def parse_fail_line(line: str) -> Stead | None:
    m = _FAIL.match(line.rstrip("\r\n"))
    if not m:
        return None
    return Stead(
        test=m["test"],
        signal=m["signal"],
        time=int(m["time"]),
        expected=int(m["expected"], 16),
        actual=int(m["actual"], 16),
        dump=m["dump"],
    )


def parse_log(path: Path | str) -> Stead | None:
    """First STEAD FAIL line in the log, or None."""
    with Path(path).open(errors="replace") as f:
        for line in f:
            s = parse_fail_line(line)
            if s is not None:
                return s
    return None
