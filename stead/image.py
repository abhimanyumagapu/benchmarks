"""Build the images the bench runs in.

    stead-tools            ubuntu + the prebuilt toolchain (once per machine)
    stead-<repo>:<commit>  FROM stead-tools; the tree at that commit with the shim applied, the recipe,
                           the clean simulator already built; /work/manifest lists the tree's files

A core has a pinned commit in repo.yaml, but a case may name another: one image per distinct commit,
all on the shared tools layer. The tree comes out of the mirror with `git archive` of the commit,
recursed into every submodule at the gitlink the commit records; a submodule the mirror lacks, or a
gitlink it never fetched, is cloned or fetched into the mirror on the way. The shim is applied to that
export before the build, so a commit it does not fit fails here, before any case exists.

push/pull move one tag to or from a registry; the image id every case records survives the trip.
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


def image_tag(repo: str, commit: str) -> str:
    return f"stead-{repo}:{commit[:7]}"


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def _submodule(mirror: Path, commit: str, path: str, sha: str) -> Path:
    """The submodule repo under the mirror, holding `sha`; cloned or fetched if it does not."""
    sub = mirror / path
    if not (sub / ".git").exists():
        blob = ["config", "--blob", f"{commit}:.gitmodules"]
        paths = _git(mirror, *blob, "--get-regexp", r"^submodule\..*\.path$").decode().split()
        name = paths[paths.index(path) - 1].removeprefix("submodule.").removesuffix(".path")
        url = _git(mirror, *blob, "--get", f"submodule.{name}.url").decode().strip()
        logger.warning("submodule %s not in the mirror; cloning %s", path, url)
        subprocess.run(["git", "clone", "-q", url, str(sub)], check=True)
    if subprocess.run(
        ["git", "-C", str(sub), "cat-file", "-e", sha], capture_output=True, check=False
    ).returncode:
        logger.warning("submodule %s lacks %s; fetching it", path, sha[:7])
        _git(sub, "fetch", "-q", "origin", sha)
    return sub


def export(mirror: Path, commit: str, dest: Path) -> list[str]:
    """Tracked files of `commit` into dest, submodules included. Returns the sorted file list."""
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-x", "-C", str(dest)], input=_git(mirror, "archive", commit), check=True)
    for line in _git(mirror, "ls-tree", "-r", commit).decode().splitlines():
        mode, _, sha, path = line.split(maxsplit=3)
        if mode == "160000":
            export(_submodule(mirror, commit, path, sha), sha, dest / path)
    return sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())


def apply_shim(tree: Path, shim: Path) -> list[str]:
    """Apply the shim file by file. A file whose hunk has since landed upstream is skipped and
    returned; a file the shim does not fit raises, so a commit needing a ported shim fails here."""
    skipped = []
    for f in patchlib.touched_files(shim.read_text()):
        argv = ["git", "apply", f"--include={f}", str(shim.resolve())]
        if not subprocess.run(argv, cwd=tree, capture_output=True, check=False).returncode:
            continue
        reverse = [*argv[:2], "-R", "--check", *argv[2:]]
        if subprocess.run(reverse, cwd=tree, capture_output=True, check=False).returncode:
            raise ValueError(f"shim does not fit {f} at this commit; port it")
        skipped.append(f)
    return skipped


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


def build_core(repo: str, mirror: Path, commit: str = "") -> tuple[str, str]:
    """The core image for `repo` at `commit` (default: repo.yaml's); returns (tag, image id)."""
    recipe_dir = REPOS / repo
    cfg = repo_cfg(repo)
    commit = commit or cfg["commit"]
    tag = image_tag(repo, commit)
    shim = recipe_dir / "shim.patch"
    if shim.exists():
        bad = [f for f in patchlib.touched_files(shim.read_text()) if matches_any(f, cfg["dut_paths"])]
        if bad:
            raise ValueError(f"shim patch touches dut_paths: {bad}")
    with tempfile.TemporaryDirectory(prefix="stead-image-") as tmp:
        ctx = Path(tmp)
        logger.info("%s: export %s from %s", repo, commit[:7], mirror)
        export(mirror, commit, ctx / "tree")
        if shim.exists():
            for f in apply_shim(ctx / "tree", shim):
                logger.info("%s: shim hunk for %s is already upstream at %s", repo, f, commit[:7])
        manifest = sorted(str(p.relative_to(ctx / "tree")) for p in (ctx / "tree").rglob("*") if p.is_file())
        (ctx / "manifest").write_text("\n".join(manifest) + "\n")
        (ctx / "recipe").mkdir()
        for f in recipe_dir.iterdir():  # what the container runs; repo.yaml is the host's and stays out
            if f.name != "repo.yaml":
                subprocess.run(["cp", "-r", str(f), str(ctx / "recipe" / f.name)], check=True)
        subprocess.run(["cp", str(recipe_dir.parent / "env.sh"), str(ctx / "env.sh")], check=True)
        logger.info("%s: docker build %s (%d files)", repo, tag, len(manifest))
        return tag, _build(ctx, "core", tag)


def push(tag: str, registry: str) -> str:
    """Push a local image as <registry>/<tag>; returns the remote tag."""
    remote = f"{registry.rstrip('/')}/{tag}"
    subprocess.run(["docker", "tag", tag, remote], check=True)
    subprocess.run(["docker", "push", remote], check=True)
    return remote


def pull(tag: str, registry: str) -> str:
    """Pull <registry>/<tag> and give it the local name every case records; returns it."""
    remote = f"{registry.rstrip('/')}/{tag}"
    subprocess.run(["docker", "pull", remote], check=True)
    subprocess.run(["docker", "tag", remote, tag], check=True)
    return tag
