"""SQLite connection helpers shared by every Rush store."""

from __future__ import annotations

import sqlite3
from types import TracebackType
from typing import Literal


class ClosingConnection(sqlite3.Connection):
    """`with` commits or rolls back, then closes. A bare `sqlite3.Connection`
    stays open after `with` until garbage collection (its statement cache is a
    reference cycle), holding committed pages in `-wal` until then."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
        /,
    ) -> Literal[False]:
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()
