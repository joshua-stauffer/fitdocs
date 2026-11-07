"""Check a post template's SQL against the index (post-templates task 2.3).

The one module in the package that imports `fitdocs.query`. It opens a
sandboxed query session and refuses, per variable and before any page is
touched, SQL that is not one `SELECT`, that does not constrain `$as_of`, that
names a parameter fitdocs does not bind, or that the lint finds unstable.
Requirements 2.1 to 2.5 and 13.3.

The lint does not parse SQL itself. DuckDB serializes the statement
(`json_serialize_sql`) and the walker below reads the JSON, so keyword column
references, calls inside subqueries, CTEs and CASE arms, and sampling are all
found the same way as at the top level.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Final, TypeVar

from fitdocs.post_template.model import Unavailable
from fitdocs.post_template.template import PostTemplate, Variable
from fitdocs.query.command import (
    OutcomeKind,
    QueryEnvironment,
    QuerySession,
    SessionUnavailable,
    open_session,
)
from fitdocs.query.statement import (
    StatementFailed,
    StatementRefused,
    StatementTimedOut,
    is_user_interrupt,
)

__all__ = [
    "BOUND_PARAMETERS",
    "CHECK_STATEMENT_TIMEOUT_S",
    "REQUIRED_PARAMETER",
    "VOLATILE_FUNCTIONS",
    "VOLATILE_KEYWORDS",
    "SessionResolver",
    "lint_findings",
    "open_resolver",
]

#: Function names whose value differs between runs, or that hide SQL from the
#: lint (`query`, `query_table`). Compared lowercased.
VOLATILE_FUNCTIONS: Final[frozenset[str]] = frozenset(
    {
        "now",
        "today",
        "current_timestamp",
        "get_current_time",
        "get_current_timestamp",
        "transaction_timestamp",
        "current_localtime",
        "current_localtimestamp",
        "random",
        "setseed",
        "uuid",
        "uuidv4",
        "uuidv7",
        "gen_random_uuid",
        "nextval",
        "currval",
        "query",
        "query_table",
        # Clock macros, and ids that change from one run to the next.
        "ago",
        "pg_conf_load_time",
        "pg_postmaster_start_time",
        "current_transaction_id",
        "txid_current",
        "current_query_id",
        "current_connection_id",
        # The call forms of the keywords below: DuckDB accepts `current_date()`
        # and serializes it as a function call, not a column reference.
        "current_date",
        "current_time",
        "localtime",
        "localtimestamp",
    }
)

#: Names DuckDB parses as a bare column reference although they read the clock.
VOLATILE_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "current_date",
        "current_time",
        "current_timestamp",
        "localtime",
        "localtimestamp",
    }
)

#: The parameter a variable must reference, and the only two it may use.
REQUIRED_PARAMETER: Final = "as_of"
BOUND_PARAMETERS: Final[frozenset[str]] = frozenset({"as_of", "page_key"})

#: Longest a check statement may run (the lint is a parse, so this is generous).
CHECK_STATEMENT_TIMEOUT_S: Final = 30.0

_HIDES_SQL: Final[frozenset[str]] = frozenset({"query", "query_table"})

_T = TypeVar("_T")


def _one_line(message: str) -> str:
    return " ".join(message.split())


def _unavailable(reason: SessionUnavailable) -> Unavailable:
    kind = reason.kind
    if kind is OutcomeKind.NOT_BUILT:
        return Unavailable("the index is not built", "run `fitdocs index`")
    if kind is OutcomeKind.NEEDS_REBUILD:
        detail = f": {_one_line(reason.message)}" if reason.message else ""
        return Unavailable(
            f"the index needs a rebuild{detail}", "run `fitdocs index` to rebuild it"
        )
    if kind is OutcomeKind.BUSY:
        holder = (
            f" by process {reason.holder_pid}" if reason.holder_pid is not None else ""
        )
        return Unavailable(
            f"the index is locked{holder}",
            "run the command again once the other fitdocs command finishes",
        )
    detail = f": {_one_line(reason.message)}" if reason.message else ""
    return Unavailable(
        f"the query sandbox could not be verified{detail}",
        "this is a fitdocs defect; please report it",
    )


def open_resolver(
    data_root: Path, env: QueryEnvironment
) -> SessionResolver | Unavailable:
    """A resolver over a sandboxed session, or why the index cannot be used."""
    session = open_session(data_root, env)
    if isinstance(session, SessionUnavailable):
        return _unavailable(session)
    return SessionResolver(session)


def lint_findings(node: object) -> tuple[str, ...]:
    """What the lint refuses in a serialized statement, as sorted short phrases.

    Walks every dict and list, so a call inside a subquery, a CTE or a CASE arm
    is found as readily as one at the top.
    """
    found: set[str] = set()
    stack: list[object] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(current)
            continue
        if not isinstance(current, dict):
            continue
        function = current.get("function_name")
        name = function.lower() if isinstance(function, str) else None
        if name in VOLATILE_FUNCTIONS:
            if name in _HIDES_SQL:
                found.add(f"`{name}(...)` runs SQL the check cannot see")
            else:
                found.add(f"`{name}()` gives a different value on each run")
        names = current.get("column_names")
        if (
            current.get("class") == "COLUMN_REF"
            and isinstance(names, list)
            and len(names) == 1
            and isinstance(names[0], str)
            and names[0].lower() in VOLATILE_KEYWORDS
        ):
            found.add(f"`{names[0].lower()}` gives a different value on each run")
        if current.get("sample") is not None:
            found.add("sampling (`USING SAMPLE` or `TABLESAMPLE`) is not repeatable")
        stack.extend(current.values())
    return tuple(sorted(found))


class SessionResolver:
    """Checks a template's SQL over one sandboxed session."""

    def __init__(self, session: QuerySession) -> None:
        self._session = session

    def _interruptible(self, call: Callable[[], _T]) -> _T:
        """Run a session read; a Ctrl-C that DuckDB surfaced as a
        `RuntimeError` becomes the `KeyboardInterrupt` callers expect."""
        try:
            return call()
        except BaseException as exc:
            if not isinstance(exc, KeyboardInterrupt) and is_user_interrupt(exc):
                raise KeyboardInterrupt from exc
            raise

    def check(self, template: PostTemplate) -> tuple[str, ...]:
        """Every problem in the template's SQL, each naming its variable."""
        problems: list[str] = []
        for variable in template.variables:
            prefix = f"{template.path}: vars.{variable.name}.sql: "
            problems.extend(prefix + reason for reason in self._refusals(variable))
        return tuple(problems)

    def _refusals(self, variable: Variable) -> list[str]:
        sql = variable.sql
        try:
            screened = self._interruptible(lambda: self._session.screen(sql))
        except (StatementRefused, StatementFailed) as error:
            return [_one_line(str(error))]
        if screened.kind != "SELECT":
            return [f"must be a SELECT, not {screened.kind}"]
        reasons: list[str] = []
        if REQUIRED_PARAMETER not in screened.parameters:
            reasons.append(f"must reference ${REQUIRED_PARAMETER}")
        reasons.extend(
            f"uses ${name}, but only $as_of and $page_key are bound"
            for name in sorted(screened.parameters - BOUND_PARAMETERS)
        )
        reasons.extend(self._lint(sql))
        return reasons

    def _lint(self, sql: str) -> tuple[str, ...]:
        try:
            result = self._interruptible(
                lambda: self._session.run(
                    "SELECT json_serialize_sql($sql)",
                    params={"sql": sql},
                    max_rows=2,
                    timeout_s=CHECK_STATEMENT_TIMEOUT_S,
                )
            )
        except (StatementRefused, StatementFailed, StatementTimedOut) as error:
            return (f"could not be linted: {_one_line(str(error))}",)
        serialized = json.loads(str(result.rows[0][0]))
        if serialized.get("error") is True:
            message = _one_line(str(serialized.get("error_message", "unknown error")))
            return (f"could not be linted: {message}",)
        return lint_findings(serialized)

    def close(self) -> None:
        self._session.close()
