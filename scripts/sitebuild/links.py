"""Check the links the site generator does not (2.10, 2.12, 6.1, 6.3).

The generator's strict mode validates page links and same-site anchors. This
module covers what it leaves: asset targets, hero hrefs, ``.md`` targets
written as raw HTML, and GitHub URLs into the repository's ``docs/`` tree.

Build logic: standard library and ``scripts.sitebuild`` only (8.4).
"""

from __future__ import annotations

import html
import posixpath
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from scripts.sitebuild.model import Problem, SiteContent
from scripts.sitebuild.outline import page_path

DOCS_URL_PREFIX = re.compile(
    r"https?://github\.com/joshua-stauffer/fitdocs/blob/main/docs/"
)
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:")

_FENCE_OPEN = re.compile(r" {0,3}(`{3,}|~{3,})(.*)$")
_ATX = re.compile(r" {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_ESCAPE = re.compile(r"\\[!-/:-@\[-`{-~]")
_INLINE_DEST = re.compile(
    r"\]\([ \t\r\n]*"
    r"(?:<(?P<angle>[^<>\r\n]*)>|(?P<bare>(?:[^\s()]|\([^\s()]*\))*))"
    r"(?:[ \t\r\n]+(?:\"[^\"]*\"|'[^']*'|\([^()]*\)))?"
    r"[ \t\r\n]*\)"
)
_REFERENCE_DEF = re.compile(
    r"^ {0,3}\[(?!\^)[^\]\r\n]+\]:[ \t]*\n?[ \t]*"
    r"(?:<(?P<angle>[^<>\r\n]*)>|(?P<bare>\S+))",
    re.MULTILINE,
)
_HTML_TAG = re.compile(r"<[A-Za-z][^<>]*>")
_HTML_ATTR = re.compile(
    r"""(?<![\w:.-])(?:xlink:href|href|src)[ \t\r\n]*=[ \t\r\n]*"""
    r"""(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<uq>[^\s"'<>`]+))""",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Link:
    """One link target and the file line it starts on.

    ``html`` is true for a target found in a raw-HTML ``href`` / ``src``
    (``xlink:href`` included); ``unquoted`` is true when that value had no quotes.
    """

    target: str
    line: int
    html: bool = False
    unquoted: bool = False


# --- scanning ----------------------------------------------------------------


def _outside_fences(lines: list[str]) -> Iterator[tuple[int, str]]:
    """Yield ``(index, line)`` for each line that is not part of a fenced block.

    The fence lines themselves and everything between them are dropped; an
    unclosed fence runs to the end. A fence is at most three spaces indented,
    and a closing fence needs the same character and at least as many of it.
    """
    fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        if fence is not None:
            closing = re.fullmatch(r" {0,3}(`+|~+)[ \t]*", line.rstrip())
            if (
                closing
                and closing.group(1)[0] == fence[0]
                and len(closing.group(1)) >= fence[1]
            ):
                fence = None
            continue
        opening = _FENCE_OPEN.fullmatch(line)
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence = (opening.group(1)[0], len(opening.group(1)))
            continue
        yield index, line


def _blocks(lines: list[str]) -> Iterator[tuple[int, list[str]]]:
    """Yield ``(first index, lines)`` for each run of text outside fences.

    A run is broken by a blank line or a fence.
    """
    run: list[str] = []
    start = 0
    previous = -2
    for index, line in _outside_fences(lines):
        if (not line.strip() or index != previous + 1) and run:
            yield start, run
            run = []
        previous = index
        if not line.strip():
            continue
        if not run:
            start = index
        run.append(line)
    if run:
        yield start, run


def _mask(text: str) -> str:
    """Blank out code spans and backslash escapes, keeping length and newlines."""

    def blank(piece: str) -> str:
        return "".join(c if c == "\n" else " " for c in piece)

    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        escape = _ESCAPE.match(text, i)
        if escape:
            out.append(blank(escape.group(0)))
            i = escape.end()
            continue
        if text[i] != "`":
            out.append(text[i])
            i += 1
            continue
        j = i
        while j < n and text[j] == "`":
            j += 1
        size = j - i
        k = j
        end = -1
        while k < n:
            if text[k] != "`":
                k += 1
                continue
            m = k
            while m < n and text[m] == "`":
                m += 1
            if m - k == size:
                end = m
                break
            k = m
        if end < 0:
            out.append(text[i:j])
            i = j
        else:
            out.append(blank(text[i:end]))
            i = end
    return "".join(out)


def _opens(masked: str, close: int) -> bool:
    """Whether the ``]`` at ``close`` has a matching ``[`` before it."""
    depth = 1
    for i in range(close - 1, -1, -1):
        if masked[i] == "]":
            depth += 1
        elif masked[i] == "[":
            depth -= 1
            if depth == 0:
                return True
    return False


def extract_links(body: str, *, first_line: int) -> tuple[Link, ...]:
    """Every link target in ``body``, with the file line it starts on.

    ``first_line`` is the file line number of the first line of ``body``.
    Fenced code and code spans are skipped. Found: inline links and images,
    reference definitions, and raw-HTML ``href`` / ``src`` attributes inside a
    tag.
    """
    lines = body.split("\n")
    found: list[Link] = []
    for start, run in _blocks(lines):
        original = "\n".join(run)
        masked = _mask(original)
        base = first_line + start

        def line_of(offset: int, base: int = base, original: str = original) -> int:
            return base + original.count("\n", 0, offset)

        for match in _INLINE_DEST.finditer(masked):
            if not _opens(masked, match.start()):
                continue
            group = "angle" if match.group("angle") is not None else "bare"
            target = original[match.start(group) : match.end(group)]
            if target:
                found.append(Link(target, line_of(match.start(group))))
        for match in _REFERENCE_DEF.finditer(masked):
            group = "angle" if match.group("angle") is not None else "bare"
            target = original[match.start(group) : match.end(group)]
            if target:
                found.append(Link(target, line_of(match.start(group))))
        for tag in _HTML_TAG.finditer(masked):
            for attr in _HTML_ATTR.finditer(original, tag.start(), tag.end()):
                group = next(g for g in ("dq", "sq", "uq") if attr.group(g) is not None)
                target = html.unescape(attr.group(group)).strip()
                if target:
                    found.append(
                        Link(target, line_of(attr.start(group)), True, group == "uq")
                    )
    found.sort(key=lambda link: link.line)
    return tuple(found)


# --- GitHub heading slugs ----------------------------------------------------

_DROPPED_CATEGORIES = frozenset(
    ("Pe", "Pf", "Pi", "Ps", "Po", "Pd", "Cc", "Cf", "Co", "Cn", "No")
)


# github-slugger removes its categories *except* Alphabetic code points. The
# only Alphabetic code points in the removed categories are these So ranges
# (circled, squared, negative-circled and negative-squared Latin letters;
# parenthesized letters are not Alphabetic and are removed).
_ALPHABETIC_SYMBOLS = (
    (0x24B6, 0x24E9),
    (0x1F130, 0x1F149),
    (0x1F150, 0x1F169),
    (0x1F170, 0x1F189),
)


def _keeps(char: str) -> bool:
    if char in "- ":
        return True
    if any(low <= ord(char) <= high for low, high in _ALPHABETIC_SYMBOLS):
        return True
    category = unicodedata.category(char)
    return category[0] not in "SZ" and category not in _DROPPED_CATEGORIES


def github_slugs(markdown: str) -> frozenset[str]:
    """The heading anchors GitHub generates for ``markdown`` (github-slugger v2).

    ATX headings outside fenced code, lowercased; every character whose Unicode
    category github-slugger removes is dropped (connector punctuation such as
    ``_`` is kept); each space becomes ``-``; a repeated slug gets ``-1``,
    ``-2``, ... A backtick is a symbol character, so inline-code backticks drop out
    and their text stays.

    github-slugger removes those categories except Alphabetic code points, so
    the circled, squared, negative-circled and negative-squared Latin letters
    (category So, ``_ALPHABETIC_SYMBOLS``) are kept. Its character tables are
    Unicode 13; ``unicodedata`` follows the running Python, so a code point
    assigned or recategorised after Unicode 13 may slug differently from GitHub.
    """
    slugs: set[str] = set()
    occurrences: dict[str, int] = {}
    for text in _heading_texts(markdown.split("\n")):
        base = "".join(c for c in text.lower() if _keeps(c))
        base = base.replace(" ", "-")
        slug = base
        while slug in occurrences:
            occurrences[base] += 1
            slug = f"{base}-{occurrences[base]}"
        occurrences[slug] = 0
        slugs.add(slug)
    return frozenset(slugs)


def _heading_texts(lines: list[str]) -> Iterator[str]:
    """The text of each ATX heading outside fenced code, in order."""
    for _index, line in _outside_fences(lines):
        heading = _ATX.fullmatch(line)
        if heading:
            yield heading.group(1) or ""


# --- checking ----------------------------------------------------------------


def _strip_fragment(target: str) -> tuple[str, str]:
    """``(path, fragment)`` of ``target``, with any query dropped from the path."""
    path, _hash, fragment = target.partition("#")
    return path.partition("?")[0], fragment


def _is_absolute(target: str) -> bool:
    return bool(_SCHEME.match(target)) or target.startswith("//")


def _check_docs_url(
    target: str, docs_dir: Path, cache: dict[Path, frozenset[str]]
) -> str | None:
    """The reason a ``docs/`` GitHub URL fails, or ``None`` when it passes (6.3)."""
    rest = DOCS_URL_PREFIX.sub("", target, count=1)
    rest, fragment = _strip_fragment(rest)
    relative = unquote(rest)
    candidate = (docs_dir / relative).resolve()
    root = docs_dir.resolve()
    if root not in candidate.parents or not candidate.is_file():
        return f"docs/{relative} does not exist in the repository"
    fragment = unquote(fragment)
    if not fragment or candidate.suffix != ".md":
        return None
    if candidate not in cache:
        try:
            cache[candidate] = github_slugs(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as error:
            return f"docs/{relative} cannot be read: {error.__class__.__name__}"
    if fragment not in cache[candidate]:
        return f"anchor #{fragment} matches no heading in docs/{relative}"
    return None


def _resolve(page: str, path: str) -> str | None:
    """The content-relative form of relative ``path`` written on ``page``.

    A trailing slash (or a final ``.`` / ``..`` segment) is kept as a trailing
    slash. Returns ``None`` when the path climbs out of the content root.
    """
    directory = "" if path.startswith("/") else posixpath.dirname(page)
    directory_form = path.endswith("/") or posixpath.basename(path) in (".", "..")
    joined = posixpath.normpath(posixpath.join(directory, path.lstrip("/")))
    if joined == ".." or joined.startswith("../"):
        return None
    if joined == ".":
        return ""
    return joined + "/" if directory_form else joined


def check_links(content: SiteContent, *, repo_root: Path) -> tuple[Problem, ...]:
    """Every link violation in ``content``, sorted by ``(path, where, message)``.

    Reads ``content`` and ``<repo_root>/docs/`` only.
    """
    docs_dir = repo_root / "docs"
    cache: dict[Path, frozenset[str]] = {}
    assets = {asset.path for asset in content.assets}
    page_urls = {page_path(page.path) for page in content.pages}
    problems: set[Problem] = set()

    def check_absolute_or_docs(page: str, where: str, target: str) -> None:
        if DOCS_URL_PREFIX.match(target):
            reason = _check_docs_url(target, docs_dir, cache)
            if reason is not None:
                problems.add(Problem(page, where, f"docs URL {target}: {reason}"))

    for page in content.pages:
        head = page.staged_text[: len(page.staged_text) - len(page.body)]
        first_line = 1 + head.count("\n")
        for link in extract_links(page.body, first_line=first_line):
            where = str(link.line)
            target = link.target
            if _is_absolute(target):
                check_absolute_or_docs(page.path, where, target)
                continue
            path, _fragment = _strip_fragment(target)
            if not path:
                continue
            path = unquote(path)
            if link.unquoted:
                problems.add(
                    Problem(
                        page.path,
                        where,
                        f"raw HTML link {target} has an unquoted attribute value "
                        "that the generator does not rewrite: quote the value",
                    )
                )
                continue
            if path.endswith(".md"):
                if link.html:
                    problems.add(
                        Problem(
                            page.path,
                            where,
                            f"raw HTML link to page {target}: use markdown link "
                            "syntax so the generator checks it",
                        )
                    )
                continue
            resolved = _resolve(page.path, path)
            if resolved is None:
                problems.add(
                    Problem(page.path, where, f"link {target} leaves the content root")
                )
            elif resolved not in (
                page_urls if resolved.endswith("/") or resolved == "" else assets
            ):
                hint = (
                    f"link {target} is missing its trailing slash: "
                    f"{resolved}/ is a page URL"
                    if resolved + "/" in page_urls
                    else f"link {target} is neither an included asset nor a page URL"
                )
                problems.add(Problem(page.path, where, hint))
        for index, action in enumerate(page.hero_actions or ()):
            where = f"hero_actions[{index}].href"
            href = action.href
            if _is_absolute(href):
                if href.startswith("https://"):
                    check_absolute_or_docs(page.path, where, href)
                else:
                    problems.add(
                        Problem(
                            page.path, where, f"absolute href {href} must be https://"
                        )
                    )
            elif href not in page_urls:
                problems.add(
                    Problem(
                        page.path,
                        where,
                        f"href {href} is not the URL path of an included page",
                    )
                )
    return tuple(sorted(problems, key=lambda p: (p.path, p.where, p.message)))
