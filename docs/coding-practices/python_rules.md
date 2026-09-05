# Python Rules

Style is PEP 8. Where a project config (`pyproject.toml`, `ruff.toml`, `setup.cfg`)
disagrees, the project config wins. Consistency inside a file beats the guide.

---

## Layout

| Rule | Value |
|---|---|
| Indent | 4 spaces, never tabs |
| Line length | 88 (black/ruff default); PEP 8 says 79 — follow project config |
| Docstring/comment width | 72 |
| Top-level defs | 2 blank lines |
| Methods inside a class | 1 blank line |
| File encoding | UTF-8, no coding declaration |
| End of file | one newline |

Continuation lines: align with the opening delimiter, or use a hanging indent
with nothing after the opening bracket. Closing bracket lines up with the first
character of the line that starts the construct.

Break **before** binary operators:

```python
total = (price
         + tax
         - discount)
```

---

## Imports

- One module per line. `from x import a, b` on one line is fine.
- Order, separated by blank lines: **stdlib → third-party → local**.
- Absolute imports. Explicit relative (`from . import sibling`) is acceptable
  inside a package; never implicit relative.
- No `from module import *`.
- All imports at the top, after the module docstring. Exceptions: avoiding a
  circular import, or an optional/expensive dependency — comment why.

---

## Naming

| Thing | Style |
|---|---|
| Module, package | `lower_snake` (short, no underscores if possible for packages) |
| Class, Exception | `CapWords` |
| Function, method, variable | `lower_snake` |
| Constant | `UPPER_SNAKE`, module level |
| Type variable | `CapWords`, short (`T`, `KT`) |
| Internal | `_leading_underscore` |
| Name clash with keyword | `class_`, trailing underscore |

- First arg: `self` for methods, `cls` for classmethods.
- Never use `l`, `O`, `I` as single-character names.
- Exception classes end in `Error` if they represent an error.

### Names must be descriptive

A reader should know what a name holds or does without reading the body.

- **Functions are verb phrases** (`fetch_user`, `parse_header`); **classes are
  noun phrases** (`UserCache`, `RequestParser`).
- **Booleans read as predicates**: `is_valid`, `has_token`, `should_retry`.
  Never negated — `is_not_ready` makes `if not is_not_ready` unreadable.
- **One verb per meaning** across the codebase. Pick `get_` vs `fetch_` vs
  `load_` and use it consistently; different verbs imply different behaviour.
- **No abbreviations** except universally known ones (`id`, `url`, `db`, `cfg`).
  `usr_cnt` is not shorter enough to be worth it.
- **Units in the name** when the value has one: `timeout_s`, `size_bytes`,
  `price_usd`, `delay_ms`. A bare `timeout` is a bug waiting to happen.
- **Type is not the name**: `users`, not `user_list`; `config`, not `config_dict`.
  The type hint already says it.
- **Length scales with scope**: `i` in a two-line loop is fine; a module-level
  or long-lived variable gets a full name.
- Single letters only in comprehensions, loop counters, and maths where the
  symbol is the convention (`x`, `y`, `n`).

---

## Whitespace

```python
# yes
spam(ham[1], {eggs: 2})
x = 1
def f(a, b=1, *, key=None): ...
i = i + 1
c = (a + b) * (a - b)

# no
spam( ham[ 1 ], { eggs: 2 } )
x             = 1
def f(a, b = 1): ...
c = (a+b) * (a-b)
```

- No space before `,`, `;`, `:`, or before an opening bracket/paren.
- One space either side of `=` for keyword defaults **only when annotated**:
  `def f(x: int = 0)`.
- Slices: `ham[1:9]`, `ham[lower+offset : upper+offset]` — colon acts as an
  operator with equal space on both sides when the expressions are complex.
- One statement per line. No trailing whitespace.

---

## Comments and docstrings

- Comments explain **why**, not what. Update them when the code changes; a
  wrong comment is worse than none.
- Block comments: `# ` prefix, same indent as the code below.
- Inline comments: sparse, two spaces before `#`.
- Every public module, class and function gets a docstring. Private helpers get
  one only if the behaviour is non-obvious.
- `"""One line ending in a period."""` for simple things. Multi-line: summary,
  blank line, detail, closing `"""` on its own line.
- Docstrings describe the contract (args, returns, raises), not the
  implementation. Don't repeat what the type hints already say.

---

## Programming recommendations

```python
if x is None: ...              # not == None
if not seq: ...                # not len(seq) == 0
if isinstance(x, int): ...     # not type(x) == int
if not name.startswith("a"):   # not name[:1] != "a"
```

- Comparisons to singletons (`None`, `True`, `False`) use `is` / `is not`.
- Use `is not`, not `not ... is`.
- Prefer `def f(): ...` over `f = lambda: ...`.
- Derive exceptions from `Exception`, not `BaseException`.
- Catch the narrowest exception that applies. Bare `except:` is banned;
  `except Exception:` only at a top-level boundary where you log and re-raise.
- Keep the `try` block to the single line that can raise.
- Return consistently: if any path returns a value, every path does
  (`return None` explicitly).
- Context managers (`with`) for anything that must be released.
- f-strings for formatting, except in logging calls.

---

## Type hints

- Annotate all public function signatures — args and return.
- Local variables only where the type isn't obvious.
- Modern syntax: `list[int]`, `dict[str, int]`, `X | None`. Not `List`,
  `Optional`.
- `from __future__ import annotations` if targeting <3.10 with new syntax.
- Don't annotate `self` / `cls`.
- `Any` is an admission of defeat — use it deliberately, not by default.

---

## Production rules

- **No mutable default args.** `def f(x=None)` then `x = x or []` inside.
- **No side effects at import time.** Work goes in functions; entry point behind
  `if __name__ == "__main__":`.
- **`logging`, not `print`,** in library and service code. Lazy args:
  `logger.info("got %s", n)` — never f-strings in the log call.
- **`pathlib.Path`, not `os.path`** string joining.
- **No secrets, keys, or absolute local paths in source.** Read from env or config.
- **Fail loud, fail early.** Validate inputs at the boundary; don't paper over
  bad state with a default.
- **Dataclasses / `NamedTuple`** for structured records instead of dicts of
  loose keys.
- **Deterministic output**: sort before iterating a set/dict when order matters
  to the result.
- Prefer the stdlib over a new dependency. Justify every dependency added.
- Delete dead code rather than commenting it out — git remembers.

---

## Structure

- A function does one thing. If you need "and" to describe it, split it.
- Keep functions short enough to read without scrolling; nesting deeper than
  three levels is a refactor signal.
- Pure logic separate from I/O — makes both testable.
- Module-level constants over magic numbers scattered in the body.

---

## Tests

- Every bug fix gets a regression test.
- `pytest`, plain `assert`. One behaviour per test; name says what it asserts:
  `test_returns_none_when_queue_empty`.
- Test the public contract, not private internals.
- No network, no clock, no filesystem in unit tests unless that's the subject.

---

## Tooling

Run before declaring work done:

```
ruff format .      # or black .
ruff check --fix .
mypy .             # if the project uses it
pytest
```

Never commit code that fails these. Don't add `# noqa` or `# type: ignore`
without a reason on the same line.

---

## Never

- `from x import *`
- bare `except:` / `except: pass`
- mutable default arguments
- `eval` / `exec` on anything that came from outside
- comparing types with `==`
- `print` for logging in non-CLI code
- catching an exception to silence it
- committing commented-out code, debug prints, or `TODO` without an owner
