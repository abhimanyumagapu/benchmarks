"""case.yaml: everything a solver is allowed to know about a case."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import yaml

from .fail import Stead


def matches_any(path: str, globs: list[str]) -> bool:
    # fnmatch's * crosses '/', so "rtl/**" means anything under rtl/
    return any(fnmatch(path, g) for g in globs)


@dataclass
class Case:
    id: str
    repo: str
    url: str
    commit: str
    kind: str  # injected | hwe
    test: str
    recipe: str
    dump: str | None  # path relative to case dir, or None
    validated_on: str  # e.g. verilator-5.050
    dut_paths: list[str] = field(default_factory=list)
    checker_paths: list[str] = field(default_factory=list)
    stead: Stead | None = None
    notes: str = ""

    def is_dut_path(self, path: str) -> bool:
        return matches_any(path, self.dut_paths)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stead"] = self.stead.to_dict() if self.stead else None
        return d

    def save(self, path: Path | str) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_dict(), sort_keys=False))

    @classmethod
    def load(cls, path: Path | str) -> Case:
        d = yaml.safe_load(Path(path).read_text())
        s = d.get("stead")
        if s:
            d["stead"] = Stead(
                test=s["test"],
                signal=s["signal"],
                time=int(s["time"]),
                expected=int(s["expected"], 16),
                actual=int(s["actual"], 16),
                dump=s.get("dump"),
            )
        return cls(**d)
