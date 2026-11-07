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
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, TypeVar

from fitdocs.post_template.model import (
    Binding,
    FillCode,
    Unavailable,
    VariableOutcome,
)
from fitdocs.post_template.template import PostTemplate, Variable
from fitdocs.query.command import (
    OutcomeKind,
    QueryEnvironment,
    QuerySession,
    SessionUnavailable,
    open_session,
)
from fitdocs.query.statement import (
    TIMESTAMPTZ_HINT,
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
    "RESOLVE_MAX_ROWS",
    "SessionResolver",
    "ValueRefusal",
    "lint_findings",
    "open_resolver",
    "to_text",
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

#: One row is a value; the second row is read only to prove there is one too many.
RESOLVE_MAX_ROWS: Final = 2

#: Line breaks of any kind: the title's class plus NEL and the Unicode separators.
_LINE_BREAK: Final = re.compile(r"[\n\r\v\f\x85\u2028\u2029]")
_COMMENT_MARKERS: Final[tuple[str, ...]] = ("<!--", "-->", "--!>")

_HIDES_SQL: Final[frozenset[str]] = frozenset({"query", "query_table"})

_T = TypeVar("_T")


def _one_line(message: str) -> str:
    return " ".join(message.split())


_TIMESTAMP_ADVICE: Final = (
    "returned a timestamp; cast it to text, for example "
    "strftime(..., '%H:%M'), or to DATE"
)


@dataclass(frozen=True)
class ValueRefusal:
    """A value the post cannot carry, with advice on how to return one it can."""

    detail: str


def to_text(value: object) -> str | ValueRefusal:
    """The text a non-NULL value stands for, or why it is refused.

    The order matters: a `bool` is an `int` and a `datetime` is a `date`, so
    each is tested before the type it would otherwise pass as.
    """
    if isinstance(value, bool):
        return ValueRefusal(
            "returned a boolean; cast it to text, for example "
            "CASE WHEN ... THEN 'yes' ELSE 'no' END"
        )
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            return ValueRefusal(
                f"returned {value}, which is not a number; return NULL instead"
            )
        return format(value, "f")
    if isinstance(value, float):
        return ValueRefusal(
            "returned a floating-point number, which can print differently "
            "from run to run; cast it, for example ::DECIMAL(10, 2) or "
            "round(...)::INTEGER"
        )
    if isinstance(value, datetime):
        return ValueRefusal(_TIMESTAMP_ADVICE)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        if _LINE_BREAK.search(value):
            return ValueRefusal(
                "returned text with a line break; return a single line, "
                "for example with replace(..., chr(10), ' ')"
            )
        for marker in _COMMENT_MARKERS:
            if marker in value:
                return ValueRefusal(
                    f"returned text holding {marker!r}, which would open or "
                    "close a hidden comment; remove it in the SQL"
                )
        return value
    return ValueRefusal(f"returned a {type(value).__name__} value; cast it to text")


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

    def page_is_current(self, page_key: str | None, path: str, data: bytes) -> bool:
        """Whether the index holds exactly this file for this page."""
        return self._interruptible(
            lambda: self._session.page_is_current(page_key, path, data)
        )

    def resolve(
        self, variable: Variable, binding: Binding, *, timeout_s: float
    ) -> VariableOutcome:
        """One variable's value for one page, or the code that says why not."""
        sql = variable.sql

        def failed(code: FillCode, detail: str) -> VariableOutcome:
            return VariableOutcome(variable.name, None, code, detail)

        try:
            screened = self._interruptible(lambda: self._session.screen(sql))
        except (StatementRefused, StatementFailed) as error:
            return failed(FillCode.STATEMENT_FAILED, _one_line(str(error)))
        if screened.kind != "SELECT" or screened.parameters - BOUND_PARAMETERS:
            return failed(
                FillCode.STATEMENT_FAILED,
                "must be a SELECT that uses only $as_of and $page_key",
            )
        values: dict[str, object] = {
            "as_of": binding.as_of,
            "page_key": binding.page_key,
        }
        params = {name: values[name] for name in screened.parameters}
        try:
            result = self._interruptible(
                lambda: self._session.run(
                    sql,
                    params=params,
                    max_rows=RESOLVE_MAX_ROWS,
                    timeout_s=timeout_s,
                )
            )
        except StatementTimedOut as error:
            return failed(FillCode.TIMED_OUT, _one_line(str(error)))
        except StatementFailed as error:
            if error.hint == TIMESTAMPTZ_HINT:
                return failed(FillCode.VALUE_REFUSED, _TIMESTAMP_ADVICE)
            return failed(FillCode.STATEMENT_FAILED, _one_line(str(error)))
        except StatementRefused as error:
            return failed(FillCode.STATEMENT_FAILED, _one_line(str(error)))
        if len(result.columns) != 1:
            return failed(
                FillCode.SHAPE_INVALID,
                f"must return one column; it returned {len(result.columns)}",
            )
        if len(result.rows) > 1:
            return failed(
                FillCode.SHAPE_INVALID,
                "must return at most one row; it returned more than one",
            )
        if not result.rows or result.rows[0][0] is None:
            return VariableOutcome(variable.name, None, None, None)
        text = to_text(result.rows[0][0])
        if isinstance(text, ValueRefusal):
            return failed(FillCode.VALUE_REFUSED, text.detail)
        return VariableOutcome(variable.name, text, None, None)

    def close(self) -> None:
        self._session.close()
