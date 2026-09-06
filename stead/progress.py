"""What a long-running command is doing while it does it.

A `--all` run holds several cases at once and each one disappears into a container for minutes at a
time. Two things make that legible: every line carries the case it belongs to (`tag`), and anything
that takes time says so on the way in and how long it took on the way out (`timed`).

    with tag("scr1-0001"), timed(logger, "build"):
        ...
    [stead.recipe] scr1-0001  build ...
    [stead.recipe] scr1-0001  build ok in 1m12s
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
import time
from contextlib import contextmanager

_TAG: contextvars.ContextVar[str] = contextvars.ContextVar("stead_tag", default="")


class _Tag(logging.Filter):
    """Puts whose work this line is into the record, so the format string can place it."""

    def filter(self, record: logging.LogRecord) -> bool:
        who = _TAG.get()
        record.tag = f"{who}  " if who else ""
        return True


def setup() -> None:
    """Warnings and worse by default, so a run prints its counter and nothing else.

    STEAD_LOG=info turns the per-step trace back on -- which container, which build, how long each
    took -- for when a run is stuck and the counter alone does not say where.
    """
    level = logging.getLevelName(os.environ.get("STEAD_LOG", "WARNING").upper())
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(tag)s%(message)s"))
    handler.addFilter(_Tag())
    logging.basicConfig(
        level=level if isinstance(level, int) else logging.WARNING, handlers=[handler], force=True
    )


@contextmanager
def tag(who: str):
    """Label every log line from this thread with `who`. Pool workers start with an empty context,
    so this is set inside the worker, not around the submit."""
    token = _TAG.set(who)
    try:
        yield
    finally:
        _TAG.reset(token)


def dur(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s" if m else f"{s}s"


@contextmanager
def timed(logger: logging.Logger, what: str):
    """Log `what` on the way in and how long it took on the way out.

    Reports whether the block returned or raised without catching anything: the
    exception is read off the interpreter in the `finally`, so it propagates
    untouched. Nested calls read as a trace of where the minutes went.
    """
    t0 = time.monotonic()
    logger.info("%s ...", what)
    try:
        yield
    finally:
        verdict = "failed" if sys.exc_info()[0] is not None else "ok"
        logger.info("%s %s in %s", what, verdict, dur(time.monotonic() - t0))


BAR_WIDTH = 20


class Counter:
    """`scoring [########............]  7/20`, rewritten in place as items land.

    A run is minutes to hours, and what each case scored is on the page and in its json, so the
    counter is the whole of the routine output. It redraws over itself on a terminal; where stdout
    is a pipe or a log there is no cursor to move, so each update takes its own line instead.
    Failures print above it, being the one thing a number cannot carry.
    """

    def __init__(self, what: str, total: int) -> None:
        self.what, self.total = what, total
        self.done = self.failed = 0
        self.interactive = sys.stdout.isatty()
        self.started = time.monotonic()

    def _line(self) -> str:
        filled = round(BAR_WIDTH * self.done / self.total) if self.total else BAR_WIDTH
        failed = f"  {self.failed} failed" if self.failed else ""
        return f"{self.what} [{'#' * filled}{'.' * (BAR_WIDTH - filled)}]  {self.done}/{self.total}{failed}"

    def _write(self, text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    def draw(self) -> None:
        self._write(f"\r{self._line()}" if self.interactive else f"{self._line()}\n")

    def tick(self, failure: str = "") -> None:
        """One item finished. A non-empty `failure` is counted and printed above the counter."""
        self.done += 1
        if failure:
            self.failed += 1
            # wipe the counter first, or its tail is left behind on the failure line
            self._write(f"\r{' ' * len(self._line())}\r" if self.interactive else "")
            self._write(f"{failure}\n")
        self.draw()

    def finish(self) -> None:
        """The last line stays on screen, so the tally survives the run."""
        self._write(f"\r{self._line()}  in {dur(time.monotonic() - self.started)}\n")
