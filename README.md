# Benchmarks

Benchmarks for hardware debug tools on real open-source cores, scored by simulation. LLMs,
ChipAgents, Bronco AI, CRUX and Walker are evaluated on identical cases. Each benchmark comprises a
set of cases, a harness that runs the tools against them, and a published results page.

## STEAD-Bench

Functional RTL debug. A bug on a production core becomes a case: the failing test, its logs and
waveforms, and a STEAD record naming the first incorrect signal, the time at which it went wrong, and
the expected and actual values. The tool receives the defective tree and returns ranked candidate
lines and a patch. The harness scores both by re-running the test in a container.

Five cores are supported: scr1, ibex, rocket-chip, cva6 and caliptra-rtl. Each is distributed as a
Docker image containing its toolchain and a warm build; every build and simulation executes in a
container of that image. Any model with an API key can be evaluated today. ChipAgents, Bronco, CRUX
and Walker integrate as additional agents, returning the same submission format and scored
identically.

## Contents

- [Quick start](#quick-start)
- [Requirements](#requirements)
- [Running an evaluation](#running-an-evaluation)
- [Results](#results)
- [Case contents](#case-contents)
- [Agent isolation](#agent-isolation)
- [Scoring](#scoring)
- [Adding bugs](#adding-bugs)
- [Adding a core](#adding-a-core)
- [Repository layout](#repository-layout)

## Quick start

```bash
git clone git@github.com:abhimanyumagapu/benchmarks.git && cd benchmarks
uv sync && source .venv/bin/activate
stead pull --all ghcr.io/abhimanyumagapu        # container images
stead bake --all specs                          # build cases from specs
export ANTHROPIC_API_KEY=...
stead solve --all anthropic/claude-sonnet-4-5+high 3
stead score --all
stead table
```

## Requirements

- **Platform.** Linux with Docker and BuildKit, with the invoking user in the `docker` group; or
  Apple Silicon macOS with Docker Desktop or OrbStack. The images are arm64. Allocate at least 16 GB
  of memory so that cva6 and caliptra-rtl build.
- **Python.** 3.10 or later. `uv sync` installs the locked versions from `uv.lock`;
  `pip install -e '.[dev]'` is also supported.
- **Disk.** Approximately 18 GB for all five cores, under 9 GB for a single core. Pulling one core
  also retrieves the shared toolchain layer.
- **Credentials.** The API key for each provider evaluated must be present in the environment. No
  credentials are read from configuration files.

## Running an evaluation

### Solve

`stead solve --all <method> [trials]` evaluates a method against every case without a result.

| Method | Requires | Example |
|---|---|---|
| `anthropic/<model>` | `ANTHROPIC_API_KEY` | `anthropic/claude-fable-5-1` |
| `openai/<model>` | `OPENAI_API_KEY` | `openai/gpt-5` |
| `xai/<model>` | `XAI_API_KEY` | `xai/grok-4.6` |
| `gemini/<model>` | `GEMINI_API_KEY` | `gemini/gemini-2.5-pro` |
| `openrouter/<org>/<model>` | `OPENROUTER_API_KEY` | `openrouter/deepseek/deepseek-r1` |
| `claude`, `claude-<alias>` | Claude Code login | `claude-sonnet`, `claude-opus` |

Any provider supported by litellm may be used. The `+<effort>` suffix sets reasoning effort and is
recorded with the result.

All methods receive identical inputs:

- **Prompt.** `prompts/system.md`, followed by `skills/rtl-debug/SKILL.md` and, where present,
  `skills/<repo>/SKILL.md`.
- **Tools.** File read, grep, glob, edit restricted to `tree/`, Python with pywellen, and `sim`,
  which rebuilds the edited tree and runs a single test in the core's simulator. Claude Code methods
  use their native tools together with `stead-sim`.
- **Scripts.** The `tools/` directory within the case, comprising the shared scripts from
  `skills/tools/` and any core-specific scripts.

The `trials` argument sets the number of independent runs per case. Because model output is
non-deterministic, a case is counted as resolved if any trial succeeds, reported as pass@k. Cost
scales with the trial count.

Every run retains its transcript and is retried twice following a crash. A run that continues to fail
is recorded as a miss with the corresponding error.

### Selective execution

`--all` resumes rather than restarts: cases with an existing result are skipped. The following flags
narrow execution further and may appear anywhere in the command.

| Flag | Effect |
|---|---|
| `--repo <names>` | Restrict to the named cores |
| `--case <ids>` | Restrict to the named cases |
| `--force` | Recompute results that already exist (solve and score) |

```bash
stead solve --all xai/grok-4.6 --repo ibex,scr1
stead solve cases/ibex/ibex-0001 xai/grok-4.6 3
stead score --all --repo ibex --force
stead table --repo ibex
```

Bake does not recompute an existing case. Remove the case directory to rebuild it.

### Score

`stead score --all` evaluates every result without a verdict. Ranked lines are compared against the
gold window, and the patch is validated by rebuilding the tree and re-running the affected tests in a
fresh container.

Patch validation requires a full rebuild per submission and is the dominant cost of an evaluation.
Cores are scored concurrently, so total elapsed time is governed by the slowest core rather than the
sum of all cores. Each verdict records its own `score_wall_s`.

### Table

`stead table` writes `results/index.html` and prints the leaderboard to standard output. The page is
a single self-contained file with no external dependencies and no build step. It may be served
directly from `results/` or published via GitHub Pages.

### Console output and environment

A run reports a single progress counter together with any failures:

```
scoring [############........]  3/5
```

| Variable | Default | Effect |
|---|---|---|
| `STEAD_LOG` | `warning` | Set to `info` for a per-stage trace of container, build and test timings |
| `STEAD_JOBS` | `4` | Maximum containers in flight across all cores |

The per-core `jobs` value in `repo.yaml` continues to bound each core independently.

## Results

```
results/<case>/<method>.json               submission as returned, never modified
results/<case>/<method>.score.json         verdict
results/<case>/<method>.trajectory.jsonl   transcript: messages, tool calls, reasoning
results/index.html                         published page
```

The page presents one row per method, reporting resolved rate, agent, effort, trial count, execution
window, hit@k, file@k, patches fixed, errors, flagged runs, unconfined runs, total cost, and solve and
score durations. Per-trial results follow, together with breakdowns by core and by bug class. Columns
are sortable and case rows are filterable.

`cases/` and `gold/` are not tracked in version control. Both are produced by `stead bake --all specs`
from `specs/` and the container images, identically on every machine. The specs are the authoritative
definition of the benchmark.

## Case contents

Each case directory, `cases/<repo>/<id>/`, contains:

| File | Contents |
|---|---|
| `logs/fail.log` | The failing run, alongside every other log it produced |
| `waves/fail.fst` | The waveform dump of that run |
| `case.yaml` | Core, commit, image and image id, test, STEAD record, `also_fails`, DUT and checker paths |
| `README.md` | The brief presented to the tool |

The STEAD record is validated at bake time: the harness opens the failing waveform and confirms that
the signal holds the recorded value at the recorded time. A case for which the checker yields no
verifiable record is published with `stead: null`.

Certain material is withheld by design. The source tree is not included in the case; it is
materialized from the image on demand with the bug applied, without version control history and
without build output, so that the code may be read but not differenced. The passing run is verified
at bake time and not distributed, as a passing waveform alongside the failing one would disclose the
defect. The bug patch and gold window reside in `gold/`, never within a case.

## Agent isolation

Agents author and execute their own Python, and are therefore confined. The confinement mechanism is
probed at startup rather than assumed, and the mechanism in force is recorded on every submission.

| Mode | Platform | Network | Reference data |
|---|---|---|---|
| `seatbelt` | macOS, `sandbox-exec` | Denied | Denied |
| `userns` | Linux, `unshare -rmn` | Denied | Denied by mount |
| `none` | Neither available | Permitted | Permitted |

Reference data comprises `gold/`, `specs/` and `results/`: the bug patch, the gold window, and prior
submissions. Agents are given `sys.executable`, which identifies the repository root, so access to
these paths is denied explicitly rather than left undiscoverable.

`none` occurs where unprivileged user namespaces are prohibited, including GitHub-hosted runners and
hardened distributions. Under that mode transcript auditing is the sole remaining control:
transcripts are scanned for network and history access, matches are flagged, and the results page
reports the count of unconfined runs.

## Scoring

**Ranked lines.** Up to k entries, ordered by confidence. `hit_rank` is the first entry falling
within the gold window; `file_rank` is the first entry in the correct file. Reported as hit@k and
file@k.

**Patch.** Never compared against the gold patch. It must modify only DUT paths, apply cleanly over
the bug, build successfully, and take the named test and every `also_fails` test from FAIL to PASS in
a fresh container.

**Text.** Retained for adjudication; not yet scored automatically.

An alternative but correct fix is accepted. A fix that resolves the named test while regressing
related tests is not. A crash or malformed submission is recorded as a miss and never aborts the
batch. A patch that modifies the testbench is rejected.

## Adding bugs

A spec consists of a YAML file and a patch under `specs/<repo>/`. The patch is a unified diff against
the pinned commit and may modify only the DUT paths declared in `repo.yaml`.

```yaml
id: scr1-0007
test: arch_xor-01.hex            # or: auto, with suite: <regex> to screen a subset
bug_patch: scr1-0007.patch
gold: {file: src/core/pipeline/scr1_pipe_ialu.sv, start: 571, end: 571, class: stuck-bit}
commit: 8b1712f                  # optional; defaults to the commit in repo.yaml
```

```bash
stead bake --all specs    # every spec without a case, producing cases/ and gold/
stead check --all         # image id, STEAD record against waveform, clean PASS, defective FAIL
```

Bake runs the test against the clean tree, applies the bug, rebuilds, re-runs with waveform capture
enabled, validates the STEAD record, and writes the case. A spec is rejected if the clean tree fails,
if the defective tree passes or crashes, or if the patch modifies files outside the DUT.

Setting `test: auto` runs the full suite against the defective tree and selects the failing test.
The test should be named explicitly for cva6 and caliptra-rtl, where full suite execution is
prolonged. A spec specifying `commit:` is baked against that commit's image, produced by
`stead image <repo> <mirror> <commit>`.

## Adding a core

`repos/<repo>/` contains three files, all incorporated into the image.

**`repo.yaml`** declares `url`, `commit`, `validated_on`, `dut_paths`, `checker_paths` and `jobs`.

**`run.sh`** implements three verbs, executed inside the container against `/work/tree`:

```
run.sh build <tree>                                   0 ok | 2 build error
run.sh run   <tree> <test> <out> [--dump=on|off]      0 PASS | 1 FAIL | 2 build error | 3 crash
run.sh suite <tree> <out> [<regex>]                   0 ran  | 2 build error
```

`run` writes `<out>/sim.log`, containing the STEAD FAIL record on a value-check failure, and
`<out>/dump.fst` when capture is enabled. `suite` writes `<out>/summary.txt` with one `<exit> <test>`
entry per test.

**`shim.patch`** is optional. It applies a testbench modification that emits the STEAD record and may
not modify `dut_paths`. It is applied file by file prior to the build; a hunk already present
upstream is skipped, and a file it fails to apply to raises an error at `stead image`, before any
case exists. Late build fixes belong here, allowing older commits to build against the pinned
toolchain.

Historical reach differs by core. scr1, rocket-chip and cva6 bake against commits up to a year old,
bounded by the shim. ibex and caliptra-rtl reach approximately three months, bounded by the
toolchain: an older fusesoc, a Verilator warning promoted to an error, and firmware C rejected by
GCC 15.

```bash
stead image tools ~/stead-tools
stead image <repo> ~/mirrors/<repo> [<commit>]
stead push --all ghcr.io/abhimanyumagapu        # after docker login ghcr.io
```

Modifying `run.sh` or the shim requires rebuilding the image, as each case records the image id it
was baked from and `stead check` rejects any other. `repo.yaml` is read on the host, so `jobs` and
path declarations may change without a rebuild. Cores are never vendored; the image holds the tree,
one image per distinct commit over a shared toolchain layer. `stead pull --all` retrieves every image
referenced by a case.

## Repository layout

```
stead/           harness: image, container, recipe, bake, solve, score, check, ship, table
stead/agents/    one module per tool: claude_code (Claude Code headless), llm (litellm)
prompts/         the system prompt issued to every method
skills/          the rtl-debug skill appended to it
repos/           per-core recipe: run.sh, repo.yaml, shim.patch; the Dockerfile
specs/           bug specs: YAML and patch
cases/           baked cases: logs, waveforms, case.yaml, README
gold/            bug patch and gold window per case, never within a case
results/         submissions, verdicts, transcripts, published page
tests/           24 tests against a fake core image, executed in real containers
```

`ruff format . && ruff check --fix . && python -m pytest -q` must pass before any change. CI enforces
the same on every push.

## License

Apache 2.0. See `LICENSE`.
