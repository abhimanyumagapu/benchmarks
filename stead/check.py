"""Re-validate a baked case against its image: the test passes warm, fails with the bug, and the
STEAD record still agrees with the fail wave."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from . import container
from .case import Case
from .recipe import RunStatus, apply_patch, build, run
from .validate import validate_stead


def check(case_dir: Path, gold_dir: Path) -> str:
    """'ok', or the first rule the case breaks."""
    case = Case.load(case_dir / "case.yaml")
    if case.image_digest != container.image_id(case.image):
        return f"image {case.image} is not the one the case was baked from"
    if case.stead:
        ok, why = validate_stead(case.stead, case_dir / case.stead.dump)
        if not ok:
            return f"STEAD: {why}"
    tmp = Path(tempfile.mkdtemp(prefix=f"stead-check-{case.id}-"))
    cid = container.start(case.image)
    try:
        if run(cid, case.test, tmp / "pass", dump=False).status is not RunStatus.PASS:
            return "clean tree does not PASS"
        apply_patch(cid, (gold_dir / "bug.patch").read_text())
        build(cid)
        for i, test in enumerate([case.test, *case.also_fails]):
            if run(cid, test, tmp / f"fail-{i}", dump=False).status is not RunStatus.FAIL:
                return f"buggy tree does not FAIL {test}"  # a CRASH may have killed the container: stop here
    finally:
        container.stop(cid)
        shutil.rmtree(tmp, ignore_errors=True)
    return "ok"
