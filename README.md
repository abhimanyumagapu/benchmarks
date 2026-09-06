# Benchmarks

Benchmarks for hardware debug tools on real open-source cores, scored by simulation: LLMs,
ChipAgents, Bronco AI, CRUX, Walker, on the same cases. Each benchmark is a set of cases, a harness
that runs the tools on them, and a results page.

## STEAD-Bench

Functional RTL debug. A bug on a real core becomes a case: the failing test, its logs and waves, and
a STEAD line naming the first wrong signal, the time it went wrong, the expected and the actual
value. The tool gets the buggy tree and hands back ranked lines and a patch. The harness scores both
by re-running the test in a container.

Five cores: scr1, ibex, rocket-chip, cva6, caliptra-rtl. Each lives in a Docker image with its
toolchain and a warm build; every build and simulation runs in a container of that image. Any LLM
with an API key runs today; ChipAgents, Bronco, CRUX and Walker plug in as agents next to it, each
handing back the same file and scored the same way.

## Contents

- [Quick start](#quick-start)
- [Installation](#installation)
- [Running an evaluation](#running-an-evaluation)
- [Results](#results)
- [What a case is](#what-a-case-is)
- [Scoring](#scoring)
- [Adding bugs](#adding-bugs)
- [Adding a core](#adding-a-core)
- [Repository layout](#repository-layout)

## Quick start

```bash
git clone git@github.com:abhimanyumagapu/benchmarks.git && cd benchmarks
uv sync && source .venv/bin/activate              # or: pip install -e '.[dev]'
stead pull --all ghcr.io/abhimanyumagapu           # the images, once (~18 GB; or one core: stead pull scr1 ...)
stead bake --all specs                             # the cases, from the specs, on those images
export ANTHROPIC_API_KEY=...
stead solve --all anthropic/claude-sonnet-4-5+high 3   # <provider>/<model>[+<effort>] [trials]
stead score --all
stead table                                        # -> results/table.md
```

## Installation

- Linux, Docker with BuildKit (`docker.io docker-buildx`), your user in the `docker` group. Or an
  Apple Silicon Mac with Docker Desktop or OrbStack, memory set to 16 GB or more so cva6 and caliptra
  build; the images are arm64.
- Python 3.10+. `uv sync` installs the locked versions (`uv.lock`) into `.venv`; `pip install -e '.[dev]'`
  works too.
- Disk: 18 GB for all five cores, under 9 GB for one. Pulling one core brings the shared toolchain
  layer with it: `stead pull scr1 ghcr.io/abhimanyumagapu`.
- The key of the provider you run, in the environment. Nothing is read from a config file.

## Running an evaluation

**Solve.** `stead solve --all <method> [trials]` runs the method on every case that has no result yet,
four at a time. A method is a model string or an agent name:

| method | needs | example |
|---|---|---|
| `anthropic/<model>` | `ANTHROPIC_API_KEY` | `anthropic/claude-fable-5-1` |
| `openai/<model>` | `OPENAI_API_KEY` | `openai/gpt-5` |
| `xai/<model>` | `XAI_API_KEY` | `xai/grok-4.6` |
| `gemini/<model>` | `GEMINI_API_KEY` | `gemini/gemini-2.5-pro` |
| `openrouter/<org>/<model>` | `OPENROUTER_API_KEY` | `openrouter/deepseek/deepseek-r1` |
| `claude`, `claude-<alias>` | Claude Code login | `claude-sonnet`, `claude-opus` |

Any provider litellm knows works the same way. `+<effort>` sets reasoning effort and is recorded.
Every model gets the same system prompt (`prompts/system.md`), the same skill
(`skills/rtl-debug/SKILL.md`, plus `skills/<repo>/SKILL.md` for that core when it exists) and the
same tools: read, grep, glob, edit under `tree/`, python with pywellen for the waves, and `sim`,
which rebuilds its edited tree and runs one test in the core's own simulator. `claude` methods run
Claude Code headless with its own tools plus `stead-sim`. The case folder also carries `tools/`:
generic scripts from `skills/tools/` (`sim.py`, `wave.py`) and the core's own from
`skills/<repo>/tools/`.

Trials is how many times each case is run. Models are not deterministic, so `3` runs every case
three times; a case is resolved if any trial hits, which is pass@3. Cost adds up across trials.

Every run keeps its transcript, is retried twice on a crash, and is recorded as a miss with the error
if it still fails. Transcripts are scanned for network or history access; hits are flagged on the page.

**Score.** `stead score --all` scores every result without a verdict yet: ranked lines against the
gold window, and the patch by re-running the tests in a fresh container.

**Table.** `stead table` writes `results/table.md` from every verdict on disk, all methods together.

## Results

```
results/<case>/<method>.json               what the tool handed back (ranked lines, patch, text, the
                                           raw final message), never rewritten
results/<case>/<method>.score.json         its verdict
results/<case>/<method>.trajectory.jsonl   its transcript: every message, tool call and tool result,
                                           and the model's reasoning where the provider returns it
results/table.md                           the page
```

`cases/` and `gold/` are not in git: they are what `stead bake` makes from `specs/` and the images,
identically on every machine. The specs are the source of the benchmark.

The page leads with one row per method: resolved rate (gold line in the top k), agent and effort,
trials, when it ran, hit@k, file@k, patches fixed, errors, flagged runs, total cost and wall time.
Then every trial of every case, then by repo and by bug class. Re-score by deleting a `.score.json`
and running `stead score --all`.

## What a case is

`cases/<repo>/<id>/`:

- `logs/fail.log`: the failing run.
- `waves/fail.fst`: its dump.
- `case.yaml`: repo, commit, image and its id, the test, the STEAD record, other tests the bug
  breaks (`also_fails`), DUT and checker paths.
- `README.md`: the brief the tool reads first.

The STEAD record is validated at bake time: the harness opens the fail wave and confirms the signal
holds the recorded wrong value at the recorded time. A case whose checker gives no verifiable line
ships with `stead: null`.

The tree is not in the case. It is materialized from the image on demand, with the bug applied and
exactly the files of the case's commit, no `.git` and no build output, so the tool reads the code but
can never diff it. The clean run is verified at bake time but not shipped: a passing wave next to the
failing one would hand over the answer. The bug patch and the gold window live in
`gold/<repo>/<id>/`, never in the case. The tool's python runs with the network off.

## Scoring

- **Ranked lines.** Up to k lines, best first. `hit_rank` is the rank of the first line inside the
  gold window, `file_rank` the first in the right file. The page reports hit@k and file@k.
- **Patch.** Not compared with the gold. It may touch only DUT paths, must apply on top of the bug,
  the tree must build, and the named test plus every `also_fails` test must go FAIL to PASS in a
  fresh container. A different but correct fix counts; a fix that greens one test and not the others
  does not.
- **Text.** Kept for a judge; not scored automatically yet.

A crash or a malformed answer is a miss, never an aborted batch. The checker is right by construction:
a patch that rewrites the testbench is rejected.

## Adding bugs

A spec is a yaml and a patch under `specs/<repo>/`. The patch is a unified diff against the pinned
commit and may touch only the DUT paths in `repo.yaml`.

```yaml
id: scr1-0007
test: arch_xor-01.hex            # or: auto, with suite: <regex> to screen a subset
bug_patch: scr1-0007.patch
gold: {file: src/core/pipeline/scr1_pipe_ialu.sv, start: 571, end: 571, class: stuck-bit}
commit: 8b1712f                  # optional: another commit of the core; default is repo.yaml's
```

```
stead bake --all specs           # every spec without a case: -> cases/ and gold/
stead check --all                # every case: image id, STEAD vs wave, clean PASS, buggy FAIL
```

Bake runs the test clean, applies the bug, rebuilds, runs it again with the dump on, validates the
STEAD line, and writes the case. A spec is refused if the clean tree fails, the buggy tree passes or
crashes, or the patch leaves the DUT. With `test: auto` the whole suite runs on the buggy tree and the
failing test is picked; name the test on cva6 and caliptra, where the full suite takes hours. A spec
with a `commit:` bakes on that commit's image, built with `stead image <repo> <mirror> <commit>`.

Per bug on one machine: scr1 and ibex under a minute, rocket-chip 1.5 min, cva6 and caliptra 5 to
8 min. `bake --all` runs one repo at a time, `jobs` containers in parallel, and skips specs that
already have a case.

## Adding a core

`repos/<repo>/` holds three files, all baked into the image:

- `repo.yaml`: `url`, `commit`, `validated_on`, `dut_paths`, `checker_paths`, `jobs`.
- `run.sh`: three verbs, run inside the container against `/work/tree`.
  ```
  run.sh build <tree>                                   0 ok | 2 build error
  run.sh run   <tree> <test> <out> [--dump=on|off]      0 PASS | 1 FAIL | 2 build error | 3 crash
  run.sh suite <tree> <out> [<regex>]                   0 ran  | 2 build error
  ```
  `run` writes `<out>/sim.log`, with the STEAD FAIL line on a value-check fail, and `<out>/dump.fst`
  when the dump is on. `suite` writes `<out>/summary.txt`, one `<exit> <test>` per test.
- `shim.patch` (optional): a testbench edit that prints the STEAD line; it may not touch `dut_paths`.
  It is applied to the exported tree before the build, file by file: a hunk that has since landed
  upstream is skipped, a file the shim does not fit fails at `stead image`, before any case exists.
  That is also where a core's own late build fixes go so older commits build on the pinned toolchain
  (scr1 carries two such hunks). The three shims (scr1, rocket-chip, cva6) reach a year back. The
  toolchain sets the other limit: scr1, rocket-chip and cva6 build and bake a year back; ibex and
  caliptra three months back, not twelve (older fusesoc, a Verilator warning turned fatal, firmware C
  that GCC 15 rejects).

```
stead image tools ~/stead-tools              # the toolchain image, once per machine
stead image <repo> ~/mirrors/<repo> [<commit>]   # export the commit from a mirror, apply the shim, warm build
stead push --all ghcr.io/abhimanyumagapu     # after `docker login ghcr.io`
```

Editing `run.sh` or the shim means `stead image <repo>` again: a case records the image id it was
baked from and `stead check` refuses any other. `repo.yaml` is read on the host only, so `jobs` and
paths can change without a rebuild. Cores are never vendored; the image holds the tree.
One image per distinct commit, all on the shared toolchain layer; a submodule the mirror lacks at an
older commit is cloned or fetched into the mirror on the way. `stead pull --all` fetches every image
any case records.

## Repository layout

```
stead/           the harness: image, container, recipe, bake, solve, score, check, ship, table
stead/agents/    one module per tool: claude_code (Claude Code headless), llm (any model via litellm)
prompts/         the system prompt every model gets
skills/          the rtl-debug skill appended to it
repos/           per-core recipe: run.sh, repo.yaml, shim.patch; the Dockerfile
specs/           bug specs: yaml + patch
cases/           baked cases: logs, waves, case.yaml, README
gold/            bug patch and gold window per case, never inside a case
results/         submissions, verdicts, transcripts, the page
tests/           23 tests against a fake core image, in real containers
```

Tests: `ruff format . && ruff check --fix . && python -m pytest -q`. CI runs the same on every push.

## License

Apache 2.0, see `LICENSE`.
