"""A buggy source tree for a solver: the image's manifest with the bug applied, nothing else.

No build output (a clean build next to a buggy tree is a diff oracle), no .git, no patch file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from . import container
from . import patch as patchlib
from .progress import timed
from .recipe import TREE, apply_patch

logger = logging.getLogger("stead.tree")

_EXPORT = (
    "mkdir -p /work/export && cd /work/tree && cat /work/manifest /work/touched | sort -u"
    ' | while read -r f; do [ -f "$f" ] && printf \'%s\\n\' "$f"; done'
    " | tar -cf - -T - | tar -xf - -C /work/export"
)


def materialize(image: str, bug_patch: str, dest: Path) -> None:
    cid = container.start(image)
    try:
        with timed(logger, "materialize tree"):
            apply_patch(cid, bug_patch)
            # files the bug patch adds are not in the manifest; ones it deletes are skipped by the [ -f ]
            container.put(cid, "\n".join(patchlib.touched_files(bug_patch)) + "\n", "/work/touched")
            p = container.run(cid, "sh", "-c", _EXPORT, cwd=TREE)
            if p.returncode != 0:
                raise RuntimeError(f"materialize: {p.stderr}")
            container.get(cid, "/work/export", dest)
    finally:
        container.stop(cid)
