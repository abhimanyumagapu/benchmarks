"""Build the images the bench runs in.

    stead-tools            ubuntu + the prebuilt toolchain (once per machine)
    stead-<repo>:<commit>  FROM stead-tools; the pinned commit at /work/tree, shim applied,
                           clean simulator already built; /work/manifest lists the tree's files

push(repo, registry) retags the core image under a registry (ghcr.io/<owner>) and pushes it; the
image id, which every case records, survives push and pull. Pulling is `docker pull` + `docker tag`
back to the local name.

The tree comes out of the mirror with `git archive` of the commit, recursed into every submodule
at the gitlink the commit records, so the mirror's working tree is never read.
"""

from __future__ import annotations

import logging
import subprocess
import tarfile
import tempfile
from pathlib import Path

import yaml

from . import container
from . import patch as patchlib
from .case import matches_any

REPOS = Path("repos")
DOCKERFILE = Path(__file__).parent.parent / "repos" / "Dockerfile"
TOOLS_TAG = "stead-tools"
TOOLS_SKIP = ("verilator-src", "spike-src")
HOME_CACHES = (".mill", ".cache/mill", ".cache/coursier")  # mill builds offline from these
logger = logging.getLogger("stead.image")


def repo_cfg(repo: str) -> dict:
    """repos/<repo>/repo.yaml: url, commit, validated_on, dut_paths, checker_paths, jobs."""
    return yaml.safe_load((REPOS / repo / "repo.yaml").read_text())


def image_tag(repo: str, cfg: dict) -> str:
    return f"stead-{repo}:{cfg['commit'][:7]}"


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def export(mirror: Path, commit: str, dest: Path) -> list[str]:
    """Tracked files of `commit` into dest, submodules included. Returns the sorted file list."""
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=_git(mirror, "archive", commit), check=True)
    for line in _git(mirror, "ls-tree", "-r", commit).decode().splitlines():
        mode, _, sha, path = line.split(maxsplit=3)
        if mode != "160000":
            continue
        if not (mirror / path / ".git").exists():
            logger.warning("submodule %s not initialised in the mirror; exported empty", path)
            continue
        export(mirror / path, sha, dest / path)
    return sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())


def _build(ctx: Path, target: str, tag: str) -> str:
    subprocess.run(
        ["docker", "build", "-f", str(DOCKERFILE), "--target", target, "-t", tag, str(ctx)], check=True
    )
    return container.image_id(tag)


def build_tools(tools: Path) -> str:
    """The toolchain image from a prebuilt tools dir (and the mill caches in $HOME)."""
    with tempfile.TemporaryDirectory(prefix="stead-image-") as tmp:
        ctx = Path(tmp)
        logger.info("packing %s", tools)
        with tarfile.open(ctx / "tools.tar", "w") as tar:
            for p in sorted(tools.iterdir()):
                if p.name not in TOOLS_SKIP:
                    tar.add(p, arcname=p.name)
        with tarfile.open(ctx / "home.tar", "w") as tar:
            for rel in HOME_CACHES:
                if (Path.home() / rel).exists():
                    tar.add(Path.home() / rel, arcname=rel)
        return _build(ctx, "tools", TOOLS_TAG)


def build_core(repo: str, mirror: Path) -> tuple[str, str]:
    """The core image for `repo` from repos/<repo>/; returns (tag, image id)."""
    recipe_dir = REPOS / repo
    cfg = repo_cfg(repo)
    tag = image_tag(repo, cfg)
    shim = recipe_dir / "shim.patch"
    if shim.exists():
        bad = [f for f in patchlib.touched_files(shim.read_text()) if matches_any(f, cfg["dut_paths"])]
        if bad:
            raise ValueError(f"shim patch touches dut_paths: {bad}")
    with tempfile.TemporaryDirectory(prefix="stead-image-") as tmp:
        ctx = Path(tmp)
        logger.info("%s: export %s from %s", repo, cfg["commit"], mirror)
        manifest = export(mirror, cfg["commit"], ctx / "tree")
        (ctx / "manifest").write_text("\n".join(manifest) + "\n")
        subprocess.run(["cp", "-r", str(recipe_dir), str(ctx / "recipe")], check=True)
        subprocess.run(["cp", str(recipe_dir.parent / "env.sh"), str(ctx / "env.sh")], check=True)
        (ctx / "recipe" / "shim.patch").touch()  # the Dockerfile applies it when non-empty
        logger.info("%s: docker build %s (%d files)", repo, tag, len(manifest))
        return tag, _build(ctx, "core", tag)


def push(repo: str, registry: str) -> str:
    """Push stead-<repo>:<commit> (or stead-tools) as <registry>/<tag>; returns the remote tag."""
    local = TOOLS_TAG if repo == "tools" else image_tag(repo, repo_cfg(repo))
    remote = f"{registry.rstrip('/')}/{local}"
    subprocess.run(["docker", "tag", local, remote], check=True)
    subprocess.run(["docker", "push", remote], check=True)
    return remote


def pull(repo: str, registry: str) -> str:
    """Pull <registry>/<tag> and give it the local name every case records; returns the local tag."""
    local = TOOLS_TAG if repo == "tools" else image_tag(repo, repo_cfg(repo))
    remote = f"{registry.rstrip('/')}/{local}"
    subprocess.run(["docker", "pull", remote], check=True)
    subprocess.run(["docker", "tag", remote, local], check=True)
    return local
