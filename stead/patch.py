"""The files a unified diff touches; bake checks the bug patch and score the fix patch against dut_paths."""

from __future__ import annotations

import re

_HDR = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)")


def touched_files(patch: str) -> list[str]:
    files = []
    for line in patch.splitlines():
        m = _HDR.match(line)
        if m and m.group(1) != "/dev/null" and m.group(1) not in files:
            files.append(m.group(1))
    return files
