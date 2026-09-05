"""Containers over the docker CLI. One container per stage; nothing survives it but what get()
copied out. A container is a writable overlay on a core image: /work/recipe/run.sh, /work/tree
(clean simulator already built), /work/manifest."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def _docker(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=True)


def start(image: str) -> str:
    """A running container of `image`; returns its id."""
    cid = _docker("create", image, "sleep", "infinity").stdout.strip()
    _docker("start", cid)
    return cid


def run(
    cid: str, *argv: str, timeout: int | None = None, cwd: str = "/work", env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """`argv` inside the container. On timeout the container is killed and TimeoutExpired is raised."""
    flags = [f for k, v in (env or {}).items() for f in ("-e", f"{k}={v}")]
    try:
        return subprocess.run(
            ["docker", "exec", "-w", cwd, *flags, cid, *argv],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", cid], capture_output=True, check=False)
        raise


def put(cid: str, text: str, path: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=Path(path).suffix, delete=False) as f:
        f.write(text)
    _docker("cp", f.name, f"{cid}:{path}")
    Path(f.name).unlink()


def get(cid: str, path: str, dest: Path) -> None:
    """Copy `path` (a file, or a directory's contents) out to `dest`."""
    dest.mkdir(parents=True, exist_ok=True)
    _docker("cp", f"{cid}:{path.rstrip('/')}/.", str(dest))


def stop(cid: str) -> None:
    subprocess.run(["docker", "rm", "-f", cid], capture_output=True, check=False)


def image_id(image: str) -> str:
    return _docker("image", "inspect", "--format", "{{.Id}}", image).stdout.strip()
