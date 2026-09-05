# STEAD-Bench

Python 3.13. `conda create -n stead python=3.13; conda activate stead; pip install -e '.[dev]'`.

Design: `docs/stead-bench-plan.md`. Harness: `stead/`. Tests: `tests/`.
Per-repo runners: `repos/<repo>/run.sh` (contract in `stead/recipe.py`).

## Simple and minimal

- Write the least code that does the job. Nothing speculative: no option, parameter, field,
  or helper without a caller today. If a later step needs it, add it then.
- Use the engine, own only what it does not do: `git`, `pywellen`, `run.sh` via `subprocess`.
  No wrapper class, no facade over a library.
- Plain data: dataclasses and dicts. No frameworks, no class hierarchies, no registries.
- A function does one thing. C901 is capped at 12; split the function, never raise the cap.
- Before adding code, re-read the module and delete what the new code makes unnecessary.

## Tests

- Test first: watch it fail, then write the code.
- No mocks. Tests run the real code against `tests/fixtures/fakerepo/run.sh` (the `run.sh`
  contract) and a tiny VCD. Every module has a test file.

## Before finishing any Python change

```
ruff format .
ruff check --fix .
python -m pytest -q
```

All three clean, or it is not done. No `# noqa` without a reason on the same line.

Style: `docs/coding-practices/python_rules.md` (ported from walker).

## Boundaries

- Harness never edits RTL. Bug and fix patches touch `dut_paths` only; the checker is frozen.
- Gold (`gold/`) never goes inside a case folder.
- Cores are not vendored. A case records `url` + `commit`; bake clones it.
- Never commit. The owner commits.
