"""The service-neutral scan (design.md "NeutralScan"; Req 14.6).

The scan covers the connectors package, its tests, and the connectors page's
own ``##`` sections (plus its preamble, treated as its own section).
:data:`NEUTRAL_SCAN_EXEMPTIONS` shipped **empty** in the ``connectors`` spec
(no online-service connector); later specs have appended their own entries,
by design a pure append -- nothing here asserts the table's size.
:func:`scan_for_unadmitted_hosts` is pinned on synthetic inputs, independent
of the real tree, and then run once for real. "The project's own" is decided
by URL prefix against a declared ``[project.urls]`` value (not by hostname
alone), matched case-insensitively on the scheme.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONNECTORS_DOC = _REPO_ROOT / "docs" / "connectors.md"


def _connectors_doc_text() -> str:
    return _CONNECTORS_DOC.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# NeutralScan (design.md "NeutralScan", Req 14.6)
# --------------------------------------------------------------------------

# The `connectors` spec shipped this table empty; `intervals-connector` appended
# the one `intervals.icu` entry (cross-spec ruling 2026-09-29) -- a pure append,
# so nothing here asserts the table's size.
NEUTRAL_SCAN_EXEMPTIONS: dict[str, frozenset[str]] = {
    "intervals.icu": frozenset(
        {
            "src/fitdocs/connectors/intervals.py",
            "tests/connectors/test_intervals.py",
            "tests/connectors/test_intervals_pull.py",
            "tests/connectors/test_intervals_publish.py",
            "tests/connectors/test_intervals_publish_cli.py",
            "tests/connectors/test_intervals_docs.py",
            "docs/connectors.md#intervals.icu",
        }
    ),
    "personal.connectapi.garmin.com": frozenset(
        {
            "src/fitdocs/connectors/garmin.py",
            "tests/connectors/test_garmin.py",
            "tests/connectors/test_garmin_fetch.py",
            "tests/connectors/test_garmin_wellness.py",
            "tests/connectors/test_garmin_pull.py",
        }
    ),
    "api.fitdocs.ai": frozenset(
        {
            "src/fitdocs/connectors/relay.py",
            "tests/connectors/test_relay.py",
            "docs/connectors.md#The relay connector",
            "docs/connectors.md#Strava",
        }
    ),
}

_URL_PATTERN = re.compile(r"https?://[^\s\"')>\]]+", re.IGNORECASE)
_RESERVED_EXACT_HOSTS = frozenset(
    {"example.com", "example.org", "example.net", "localhost"}
)
# RFC 2606 reserved: example.com/.org/.net and any of their subdomains
# (leading-dot boundary -- "notexample.com" must NOT match), plus the
# .example/.test/.invalid reserved suffixes for any host.
_RESERVED_SUFFIXES = (
    ".example.com",
    ".example.org",
    ".example.net",
    ".example",
    ".test",
    ".invalid",
)


def _extract_hosts(text: str) -> list[str]:
    hosts = []
    for match in _URL_PATTERN.finditer(text):
        host = urlparse(match.group(0)).hostname
        if host:
            hosts.append(host.lower())
    return hosts


def _is_reserved(host: str) -> bool:
    return host in _RESERVED_EXACT_HOSTS or host.endswith(_RESERVED_SUFFIXES)


def _url(host: str, path: str = "/api", scheme: str = "https") -> str:
    """Build a syntactically valid URL at runtime for a *fixture* (never a
    real service), without this file's own source text ever spelling a
    scheme and host contiguously -- the real-tree NeutralScan test below
    reads this very file's literal text, and a fixture host is deliberately
    unreserved and unadmitted so the scan can find it at all."""
    return f"{scheme}{'://'}{host}{path}"


def _own_url_prefixes() -> frozenset[str]:
    """Every declared ``[project.urls]`` value, verbatim -- "the project's
    own" is decided by URL *prefix* against one of these, not by comparing
    hostnames alone (design.md: "must be the project's own (under a
    declared [project.urls] value)")."""
    document = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    urls = document["project"]["urls"]
    return frozenset(urls.values())


def test_project_urls_declares_the_connectors_page_entry() -> None:
    """``[project.urls]`` names ``docs/connectors.md`` under the key
    "Connectors". No other test in this module notices the entry's
    deletion: the page links itself relatively, so the real-tree scan never
    needs this prefix."""
    document = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    urls = document["project"]["urls"]
    assert urls["Connectors"] == (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md"
    )


_OWN_URL_BOUNDARY_CHARS = ("/", "?", "#")


def _is_own_url(url: str, own_url_prefixes: frozenset[str]) -> bool:
    """A case-insensitive prefix match against a declared ``[project.urls]``
    value, requiring a boundary right after the matched prefix -- the end of
    the URL, or ``/``/``?``/``#`` -- so a sibling path that merely *starts
    with* the same characters (``.../fitdocs-other/x`` against the prefix
    ``.../fitdocs``) is not wrongly admitted."""
    lowered = url.lower()
    for prefix in own_url_prefixes:
        prefix_lowered = prefix.lower()
        if not lowered.startswith(prefix_lowered):
            continue
        remainder = lowered[len(prefix_lowered) :]
        if remainder == "" or remainder[0] in _OWN_URL_BOUNDARY_CHARS:
            return True
    return False


def scan_for_unadmitted_hosts(
    sources: Mapping[str, str],
    *,
    own_url_prefixes: frozenset[str],
    exemptions: Mapping[str, frozenset[str]],
) -> list[tuple[str, str]]:
    """Every ``(location, host)`` pair found in *sources* whose URL is
    neither the project's own (a case-insensitive prefix match against a
    declared ``[project.urls]`` value), nor on a reserved example host, nor
    admitted for that exact *location* by *exemptions*.

    *location* is a plain repo-relative file path, or
    ``"docs/connectors.md#<heading>"`` for one ``##`` section of the page
    (``"docs/connectors.md#"`` for its preamble before the first heading) --
    an exemption keyed by that exact string admits only that section, never
    the whole page (design.md: "a host admitted for one ``##`` section of a
    page and named in another section is [a violation]").
    """
    violations: list[tuple[str, str]] = []
    for location, text in sources.items():
        for match in _URL_PATTERN.finditer(text):
            url = match.group(0)
            if _is_own_url(url, own_url_prefixes):
                continue
            host = urlparse(url).hostname
            if host is None:
                continue
            host = host.lower()
            if _is_reserved(host):
                continue
            admitted_files = exemptions.get(host, frozenset())
            if location in admitted_files:
                continue
            violations.append((location, host))
    return violations


def _unexercised_exemptions(
    sources: Mapping[str, str], exemptions: Mapping[str, frozenset[str]]
) -> list[str]:
    """Hosts in *exemptions* that are not actually named in any of their own
    admitted files -- the conditional positive control design.md calls for
    ("so an exemption is exercised, never vacuous")."""
    unexercised = []
    for host, admitted_files in exemptions.items():
        found = any(
            host in _extract_hosts(sources.get(loc, "")) for loc in admitted_files
        )
        if not found:
            unexercised.append(host)
    return unexercised


def _read_for_scan(path: Path) -> str:
    """A file's text for the URL scan. Bytes that are not valid UTF-8 (a
    ``.DS_Store``, an image, a Latin-1 resource) become U+FFFD instead of
    raising, so no file is ever left out of the scan: a URL is ASCII and
    survives the replacement unchanged."""
    return path.read_bytes().decode("utf-8", errors="replace")


def _collect_text_sources(
    bases: tuple[Path, ...], *, relative_to: Path
) -> dict[str, str]:
    """Every regular, non-bytecode file under *bases*, keyed by its path
    relative to *relative_to*, read through :func:`_read_for_scan`."""
    texts: dict[str, str] = {}
    for base in bases:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            texts[str(path.relative_to(relative_to))] = _read_for_scan(path)
    return texts


# Every file under both directories, filtered only to skip bytecode caches --
# not just ``*.py`` -- so a non-Python resource under either tree is scanned
# too.
def _package_and_test_sources() -> dict[str, str]:
    return _collect_text_sources(
        (
            _REPO_ROOT / "src" / "fitdocs" / "connectors",
            _REPO_ROOT / "tests" / "connectors",
        ),
        relative_to=_REPO_ROOT,
    )


def _page_sections() -> dict[str, str]:
    """Every ``##`` section of the page, keyed by
    ``"docs/connectors.md#<heading>"``, plus the preamble before the first
    ``##`` heading (which includes the top-level ``# Connectors`` title),
    keyed by ``"docs/connectors.md#"`` (the empty heading)."""
    text = _connectors_doc_text()
    parts = re.split(r"(?m)^## (.+)$", text)
    sections: dict[str, str] = {"docs/connectors.md#": parts[0]}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections[f"docs/connectors.md#{heading}"] = body
    return sections


def _real_sources() -> dict[str, str]:
    sources = _package_and_test_sources()
    sources.update(_page_sections())
    return sources


def _real_file_listing() -> set[str]:
    """Every regular, non-bytecode file under both scanned directories,
    from a fresh walk of its own (not :func:`_package_and_test_sources`),
    for the positive control to compare against."""
    listing: set[str] = set()
    for base in (
        _REPO_ROOT / "src" / "fitdocs" / "connectors",
        _REPO_ROOT / "tests" / "connectors",
    ):
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            listing.add(str(path.relative_to(_REPO_ROOT)))
    return listing


# --- Always-on positive control: the scan really reads the real tree ------


def test_scan_file_set_matches_directory_listings_and_includes_a_page_section() -> None:
    sources = _real_sources()
    file_keys = {key for key in sources if not key.startswith("docs/connectors.md#")}
    assert file_keys == _real_file_listing()
    assert len(file_keys) > 10, "the walk is looking at the wrong directory"

    page_keys = {key for key in sources if key.startswith("docs/connectors.md#")}
    assert page_keys, "no page section was scanned"
    assert "docs/connectors.md#The ledger" in page_keys
    assert "docs/connectors.md#" in page_keys, "the page's preamble was not scanned"
    assert sources["docs/connectors.md#"].startswith("# Connectors")


def test_a_url_in_an_undecodable_file_is_still_scanned(tmp_path: Path) -> None:
    """A file that is not valid UTF-8 is read, not skipped: an unadmitted
    URL inside a Latin-1 file is still a violation, and a binary file beside
    it does not crash the walk."""
    latin1 = tmp_path / "notes.txt"
    latin1.write_bytes(f"caf\xe9 {_url(_FAKE_HOST)}\n".encode("latin-1"))
    binary_file = tmp_path / ".DS_Store"
    binary_file.write_bytes(bytes([0xFF, 0xFE, 0x00, 0x01, 0x80, 0x81]))
    with pytest.raises(UnicodeDecodeError):
        latin1.read_bytes().decode("utf-8")

    texts = _collect_text_sources((tmp_path,), relative_to=tmp_path)

    assert set(texts) == {".DS_Store", "notes.txt"}
    violations = scan_for_unadmitted_hosts(
        texts, own_url_prefixes=frozenset(), exemptions={}
    )
    assert violations == [("notes.txt", _FAKE_HOST)]


# --- Always-on: the real tree is clean --------------------------------


def test_real_tree_has_no_unadmitted_hosts() -> None:
    sources = _real_sources()
    violations = scan_for_unadmitted_hosts(
        sources,
        own_url_prefixes=_own_url_prefixes(),
        exemptions=NEUTRAL_SCAN_EXEMPTIONS,
    )
    assert violations == []


# --- Conditional control: only when the table is non-empty ----------------
# (the `intervals.icu` entry makes this loop run for real).


def test_every_exemption_entry_is_exercised_in_the_real_tree() -> None:
    sources = _real_sources()
    assert _unexercised_exemptions(sources, NEUTRAL_SCAN_EXEMPTIONS) == []


def test_the_scan_finds_the_intervals_host_in_the_connectors_own_module() -> None:
    """The generic control above is satisfied by any admitted file; this one
    pins that ``intervals.py`` itself still names the host."""
    sources = _real_sources()
    assert "intervals.icu" in _extract_hosts(
        sources["src/fitdocs/connectors/intervals.py"]
    )


def test_the_scan_finds_the_relay_host_in_the_relay_docs_section() -> None:
    """The exemption entry's section key is exercised: the section really
    names the host, so the key is not a dead string."""
    sources = _real_sources()
    assert "api.fitdocs.ai" in _extract_hosts(
        sources["docs/connectors.md#The relay connector"]
    )


def test_the_scan_finds_the_relay_host_in_the_strava_docs_section() -> None:
    """The Strava exemption key is exercised: the section really names the
    host (its default relay's policy address)."""
    sources = _real_sources()
    assert "api.fitdocs.ai" in _extract_hosts(sources["docs/connectors.md#Strava"])


def test_the_scan_finds_the_relay_host_in_the_connectors_own_module() -> None:
    """The generic control above is satisfied by any admitted file; this one
    pins that ``relay.py`` itself still names the host."""
    sources = _real_sources()
    assert "api.fitdocs.ai" in _extract_hosts(
        sources["src/fitdocs/connectors/relay.py"]
    )


# --- Synthetic unit tests of the scan function, independent of the real ---
# --- table (design.md: "pinned on synthetic inputs independent of the ----
# --- real table") -----------------------------------------------------


_FAKE_HOST = "sync.fake-vendor.net"
_OWN_URL_PREFIXES = frozenset({"https://github.com/joshua-stauffer/fitdocs"})


def test_scan_flags_an_unreserved_host_with_no_admission() -> None:
    sources = {"pkg/mod.py": f"see {_url(_FAKE_HOST)} for details"}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", _FAKE_HOST)]


def test_scan_flags_a_plain_http_url_too() -> None:
    """The scan is not scheme-specific to ``https``."""
    sources = {"pkg/mod.py": _url(_FAKE_HOST, scheme="http")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", _FAKE_HOST)]


def test_scan_matches_the_scheme_case_insensitively() -> None:
    sources = {"pkg/mod.py": _url(_FAKE_HOST, scheme="HTTPS")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", _FAKE_HOST)]


def test_scan_admits_the_same_host_for_that_exact_file() -> None:
    sources = {"pkg/mod.py": f"see {_url(_FAKE_HOST)} for details"}
    exemptions = {_FAKE_HOST: frozenset({"pkg/mod.py"})}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions=exemptions
    )
    assert violations == []


def test_scan_rejects_a_host_admitted_only_for_a_different_page_section() -> None:
    """A host admitted for one ``##`` section of the page must not be
    treated as admitted for a different section it is also named in."""
    sources = {
        "docs/connectors.md#Section A": _url(_FAKE_HOST),
        "docs/connectors.md#Section B": "nothing relevant here",
    }
    exemptions = {_FAKE_HOST: frozenset({"docs/connectors.md#Section B"})}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=frozenset(), exemptions=exemptions
    )
    assert violations == [("docs/connectors.md#Section A", _FAKE_HOST)]


def test_scan_treats_the_projects_own_url_as_admitted_everywhere() -> None:
    sources = {"pkg/mod.py": _url("github.com", "/joshua-stauffer/fitdocs")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == []


def test_scan_flags_a_lookalike_host_that_merely_contains_the_own_host_and_path() -> (
    None
):
    """Kills a wrong ``_is_own_url`` shaped as "hostname startswith own
    hostname and path startswith own path" (checked on the two fields
    separately, rather than the full URL as one prefix): under that wrong
    check, ``github.com.fake-vendor.net``'s hostname still starts with
    ``github.com`` and its path still starts with ``/joshua-stauffer/
    fitdocs``, so it would be wrongly admitted. The real, full-URL-prefix
    check never matches this host at all."""
    sources = {
        "pkg/mod.py": _url("github.com.fake-vendor.net", "/joshua-stauffer/fitdocs")
    }
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "github.com.fake-vendor.net")]


def test_scan_flags_a_sibling_repository_with_no_path_boundary() -> None:
    """A sibling repository whose path merely *starts with* the own prefix's
    path, with no separator in between (``.../fitdocs-other/x`` against the
    declared ``.../fitdocs``, which has no trailing slash), must still be
    flagged -- a bare ``str.startswith`` admits it wrongly."""
    sources = {"pkg/mod.py": _url("github.com", "/joshua-stauffer/fitdocs-other/x")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "github.com")]


def test_scan_does_not_admit_a_lookalike_host_sharing_only_a_hostname_substring() -> (
    None
):
    """ "Own" is a URL-prefix match, not a hostname check: a URL on a
    completely different host that merely happens to *contain* the
    project's own repo path as a substring must still be flagged."""
    sources = {"pkg/mod.py": _url("not-github.com", "/joshua-stauffer/fitdocs")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "not-github.com")]


def test_scan_requires_the_full_url_prefix_not_merely_the_same_host() -> None:
    """ "Own" means the URL starts with a declared ``[project.urls]`` value,
    not merely that it shares a host with one: a link to a different
    repository on the *same* host (``github.com``) must still be flagged,
    or a host-only comparison would wrongly admit any URL on that host."""
    sources = {"pkg/mod.py": _url("github.com", "/someone-else/other-repo")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=_OWN_URL_PREFIXES, exemptions={}
    )
    assert violations == [("pkg/mod.py", "github.com")]


def test_scan_treats_a_reserved_example_host_as_admitted_everywhere() -> None:
    sources = {
        "pkg/mod.py": (
            f"see {_url('api.example.com', '/v1')} and {_url('localhost:8080', '/x')}"
        )
    }
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=frozenset(), exemptions={}
    )
    assert violations == []


def test_scan_does_not_treat_an_example_lookalike_host_as_reserved() -> None:
    """Leading-dot boundary: ``notexample.com`` merely *contains*
    ``example.com`` as a substring but is not a subdomain of it, so it must
    still be flagged as an unadmitted host."""
    sources = {"pkg/mod.py": _url("notexample.com")}
    violations = scan_for_unadmitted_hosts(
        sources, own_url_prefixes=frozenset(), exemptions={}
    )
    assert violations == [("pkg/mod.py", "notexample.com")]


def test_conditional_control_flags_an_exemption_entry_none_of_its_files_names() -> None:
    """Named mutation target: an exemption table entry for a host that none
    of its own admitted files actually names is caught by
    :func:`_unexercised_exemptions` -- the mechanism the (currently
    zero-iteration) real conditional control above relies on."""
    bad_sources = {"pkg/mod.py": "no urls here at all"}
    bad_exemptions = {_FAKE_HOST: frozenset({"pkg/mod.py"})}
    assert _unexercised_exemptions(bad_sources, bad_exemptions) == [_FAKE_HOST]

    good_sources = {"pkg/mod.py": _url(_FAKE_HOST, "/x")}
    assert _unexercised_exemptions(good_sources, bad_exemptions) == []
