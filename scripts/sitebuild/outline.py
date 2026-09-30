"""The one page ordering, the URL scheme, the nav and the llms texts.

Nav, ``llms.txt`` and ``llms-full.txt`` all consume ``ordered_pages`` (3.1,
3.2, 5.1, 5.2). Pure functions of a ``SiteContent`` and plain strings: no I/O
and no clock. Its only dependency is ``scripts.sitebuild.model``.
"""

from __future__ import annotations

from scripts.sitebuild.model import SECTIONS, Page, SiteContent

_INDEX_NAME = "index.md"


def ordered_pages(
    content: SiteContent,
) -> tuple[tuple[str, tuple[Page, ...]], ...]:
    """Group pages by section in ``SECTIONS`` order, each by ascending ``order``.

    Empty sections are omitted (3.1). Pages sharing an ``order`` (which the
    loader refuses) fall back to path order so the result never depends on
    input order (5.4). A page whose section is not in ``SECTIONS`` raises
    ``ValueError`` rather than vanishing from the site.
    """
    unknown = sorted({p.section for p in content.pages} - set(SECTIONS))
    if unknown:
        raise ValueError(f"page section outside SECTIONS: {unknown[0]!r}")
    grouped: list[tuple[str, tuple[Page, ...]]] = []
    for section in SECTIONS:
        pages = sorted(
            (p for p in content.pages if p.section == section),
            key=lambda p: (p.order, p.path),
        )
        if pages:
            grouped.append((section, tuple(pages)))
    return tuple(grouped)


def page_path(page_path_md: str) -> str:
    """Map a content path to its URL path: ``""``, ``"a/"`` or ``"a/b/"`` (4.6)."""
    if page_path_md == _INDEX_NAME:
        return ""
    stem = page_path_md.removesuffix("/" + _INDEX_NAME)
    if stem != page_path_md:
        return stem + "/"
    return page_path_md.removesuffix(".md") + "/"


def nav_structure(content: SiteContent) -> list[dict[str, list[dict[str, str]]]]:
    """``[{section: [{title: path}, ...]}, ...]`` over staged ``.md`` paths (3.1)."""
    return [
        {section: [{p.title: p.path} for p in pages]}
        for section, pages in ordered_pages(content)
    ]


def _url(site_url: str, page: Page) -> str:
    return site_url.rstrip("/") + "/" + page_path(page.path)


def _lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def render_llms(
    content: SiteContent, *, site_name: str, summary: str, site_url: str
) -> str:
    """The llmstxt.org index: title, summary, then one list per section (5.1)."""
    blocks = [f"# {site_name}", f"> {summary}"]
    for section, pages in ordered_pages(content):
        lines = [f"## {section}", ""]
        lines += [f"- [{p.title}]({_url(site_url, p)}): {p.description}" for p in pages]
        blocks.append("\n".join(lines))
    return _lf("\n\n".join(blocks)) + "\n"


def render_llms_full(content: SiteContent, *, site_url: str) -> str:
    """Every page's body in navigation order, one block per page (5.2)."""
    blocks: list[str] = []
    for _section, pages in ordered_pages(content):
        for p in pages:
            head = f"# {p.title}\nSource: {_url(site_url, p)}"
            body = _lf(p.body).strip("\n")
            blocks.append(f"{head}\n\n{body}" if body else head)
    return _lf("\n\n".join(blocks)) + "\n"
