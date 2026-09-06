import subprocess
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
FAKE = "stead-fake"
COMMIT = "0" * 40
BROKEN = "1" * 40  # a second commit of the fake core: its clean tree already fails

# The fake DUT is fixtures/fakerepo/tree/rtl/alu.sv; these diffs are against it.
BUG_PATCH = (
    "--- a/rtl/alu.sv\n+++ b/rtl/alu.sv\n@@ -1,3 +1,3 @@\n module alu;\n"
    "-  assign y = a ^ b;\n+  assign y = (a ^ b) ^ 32'h10; // BUG\n endmodule\n"
)
FIX_PATCH = (
    "--- a/rtl/alu.sv\n+++ b/rtl/alu.sv\n@@ -1,3 +1,3 @@\n module alu;\n"
    "-  assign y = (a ^ b) ^ 32'h10; // BUG\n+  assign y = a ^ b;\n endmodule\n"
)


def alu_patch(line: str) -> str:
    """A bug patch replacing the DUT's one logic line with `line`."""
    return BUG_PATCH.replace("+  assign y = (a ^ b) ^ 32'h10; // BUG", "+" + line)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True).stdout


@pytest.fixture(scope="session", autouse=True)
def fake_image() -> str:
    """The fake core as an image, plus a variant whose clean tree is already broken."""
    df = FIX / "fakerepo" / "Dockerfile"
    subprocess.run(["docker", "build", "-q", "-f", df, "-t", FAKE, FIX], check=True, capture_output=True)
    subprocess.run(["docker", "tag", FAKE, f"{FAKE}:{COMMIT[:7]}"], check=True)
    subprocess.run(
        [
            "docker",
            "build",
            "-q",
            "-f",
            df,
            "--build-arg",
            "ALU_EXTRA=// BUG already here",
            "-t",
            f"{FAKE}:broken",
            FIX,
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(["docker", "tag", f"{FAKE}:broken", f"{FAKE}:{BROKEN[:7]}"], check=True)
    return FAKE


@pytest.fixture
def src_repo(tmp_path: Path) -> Path:
    """A tiny git repo shaped like a core mirror: rtl/ (DUT) and dv/ (checker)."""
    repo = tmp_path / "src"
    (repo / "rtl").mkdir(parents=True)
    (repo / "dv").mkdir()
    (repo / "rtl" / "alu.sv").write_text("module alu;\n  assign y = a ^ b;\nendmodule\n")
    (repo / "dv" / "tb.sv").write_text("module tb;\nendmodule\n")
    (repo / ".gitignore").write_text("build/\n")
    git(repo, "init", "-q")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "clean")
    return repo


def spec(tmp_path: Path, **kw):
    from stead.bake import BakeSpec
    from stead.gold import Gold

    d = dict(
        id="fake-0001",
        repo="fake",
        url="https://example.org/fake.git",
        commit=COMMIT,
        image=FAKE,
        test="xor_test",
        bug_patch=BUG_PATCH,
        gold=Gold(file="rtl/alu.sv", start=2, end=2, klass="logic"),
        dut_paths=["rtl/**"],
        checker_paths=["dv/**"],
        validated_on="fake-sim",
        out_root=tmp_path / "cases",
        gold_root=tmp_path / "gold",
    )
    return BakeSpec(**{**d, **kw})


@pytest.fixture
def baked_case(tmp_path: Path) -> Path:
    """A real baked case (fake image, XOR bit-4 bug) under tmp_path/cases."""
    from stead.bake import bake

    return bake(spec(tmp_path))
