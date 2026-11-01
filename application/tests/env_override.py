"""Set process environment variables for a test and restore them afterwards."""

import contextlib
import os
import unittest
from typing import Iterable, Iterator, Mapping, Optional


@contextlib.contextmanager
def environ_override(
    values: Optional[Mapping[str, str]] = None,
    *,
    clear: bool = False,
    unset: Iterable[str] = (),
) -> Iterator[None]:
    """Apply ``values`` to ``os.environ`` (after optionally clearing it and
    removing ``unset`` keys); the original environment is restored on exit."""
    saved = dict(os.environ)
    try:
        if clear:
            os.environ.clear()
        os.environ.update(values or {})
        for key in unset:
            os.environ.pop(key, None)
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def set_environ_for_test(
    case: unittest.TestCase,
    values: Optional[Mapping[str, str]] = None,
    *,
    clear: bool = False,
    unset: Iterable[str] = (),
) -> None:
    """Like :func:`environ_override` for a whole test: restored via ``addCleanup``."""
    stack = contextlib.ExitStack()
    stack.enter_context(environ_override(values, clear=clear, unset=unset))
    case.addCleanup(stack.close)
