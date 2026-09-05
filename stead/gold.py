"""Hidden answer for a case: the injected (or PR-fixed) line window."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


@dataclass(frozen=True)
class Gold:
    file: str
    start: int
    end: int
    klass: str = ""
    patch: str | None = None  # path of bug.patch relative to gold dir

    def hit(self, file: str, line: int) -> bool:
        return _norm(file) == _norm(self.file) and self.start <= line <= self.end

    def hit_file(self, file: str) -> bool:
        return _norm(file) == _norm(self.file)

    def save(self, path: Path | str) -> None:
        d = asdict(self)
        d["class"] = d.pop("klass")
        Path(path).write_text(yaml.safe_dump(d, sort_keys=False))

    @classmethod
    def load(cls, path: Path | str) -> Gold:
        d = yaml.safe_load(Path(path).read_text())
        d["klass"] = d.pop("class", "")
        return cls(**d)
