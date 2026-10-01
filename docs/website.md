# The website

This page documents the repository's website, the public site published at
`fitdocs.ai`, and how to build, preview and publish it. It documents the
repository's website and is not one of the contracts governed by the
[compatibility policy](compatibility.md): nothing here is part of the installed
`fitdocs` tool.

The site's copy is written by hand and kept as markdown pages in a content
directory. The site tooling reads those pages, checks them against the content
contract below, and builds a static site. `docs/` stays the single contract for
the tool itself: the site links to it by GitHub URL and never restates it.

## The content contract

The build refuses to produce a site from pages that break these rules. It
reports every violation it finds in one run (see [Failures and exit
codes](#failures-and-exit-codes)).

### Where content comes from

The content directory is the first of these that is set:

1. the `--content` option;
2. the `FITDOCS_SITE_CONTENT` environment variable;
3. `website/content/` in the repository.

An empty `FITDOCS_SITE_CONTENT` is treated as unset. An empty `--content ""` is
refused. A relative path, whether from the option or from the variable, is read
from the repository root and not from the working directory. The chosen
directory must exist: a missing one fails the run and names the directory and
which of the three sources chose it. The build never creates, changes, renames
or deletes anything in the content directory.

### Pages and assets

A file ending in `.md` is a page. Every other included file is an asset and is
copied into the site at the same relative path. A content directory with no
included page fails, and one with included pages but no `index.md` at its root
fails: `index.md` is the home page.

### Names that are excluded or refused

- A file or directory whose name begins with `_` or `.` is excluded, with
  everything beneath it. It never becomes a page or an asset. Dotfiles such as
  an editor's state file are excluded this way.
- A symbolic link anywhere in the content directory is refused, including one
  under a name that begins with `_` or `.` and one inside an excluded
  directory.
- The reserved root names `llms.txt` and `llms-full.txt` are refused at the
  root of the content directory, whatever kind of entry carries them. The build
  writes both files itself.

Reserved names are matched exactly, with letter case significant.

### Frontmatter keys

Every page begins with a line `---`, a YAML mapping with no duplicate keys, and
a closing line `---`. The file is UTF-8 with LF line endings: a file with CRLF
line endings, or with a byte-order mark before the first `---`, is refused as
having no frontmatter. A CRLF body after LF frontmatter is not refused, but see
[The annotation block](#the-annotation-block). A key not in this table is refused, and so is a value of
the wrong type. That includes the generator's own `template` key.

| Key | Type | Rule |
| --- | --- | --- |
| `title` | string | required, non-empty |
| `description` | string | required, non-empty |
| `section` | string | required, one of the sections below, exact case |
| `order` | integer | required, not a boolean; unique among the included pages of its section |
| `draft` | boolean | optional; `true` leaves the page out (see Drafts) |
| `hero_title` | string | optional, non-empty; root `index.md` only |
| `hero_tagline` | string | optional, non-empty; root `index.md` only |
| `hero_actions` | list | optional, non-empty list of action entries; root `index.md` only |

Two included pages in one section with the same `order` fail, and the message
names both files.

### Sections

The navigation is grouped by `section`, in this order. A section with no
included page is left out.

1. `Home`
2. `Why`
3. `Get started`
4. `Guides`
5. `Working with LLMs`
6. `Reference`
7. `Extend`
8. `Project`

Within a section, pages are ordered by ascending `order`.

### The home page hero

`index.md` renders with the hero layout. It shows `hero_title`, `hero_tagline`
and the `hero_actions` buttons when present, and leaves out any element whose
key is missing; it never substitutes default text. Each entry in `hero_actions`
is a mapping with these keys:

| Key | Type | Rule |
| --- | --- | --- |
| `label` | string | required, non-empty |
| `href` | string | required, non-empty; an absolute `https://` URL or a trailing-slash site path of an included page such as `get-started/install/` |
| `primary` | boolean | optional; `true` styles the button as the primary action |

An entry with any other key fails. A hero key on any page other than the root
`index.md` fails, a nested `guides/index.md` included.

### Drafts

A page with `draft: true` is left out of the navigation, the built site, search
and both site indexes. Its other frontmatter is still checked. A link to a
draft page fails, the same as a link to a page that does not exist.

### Links

Links between pages use markdown link syntax with a relative path to the
target's `.md` source file, optionally followed by an `#anchor`. The anchor must
match the heading's id as the site generator makes it, which differs from
GitHub's slug for punctuation runs and non-ASCII letters: `## Foo & Bar!` is
`#foo-bar` and `# Café -- Über_x` is `#cafe-uber_x`, where GitHub would give
`#foo--bar` and `#café----über_x`. A raw-HTML link to a `.md` source file is
refused, and the message names the file and line. A raw-HTML link to a page
URL such as `get-started/install/` is accepted.

Assets are linked by relative path. Every relative target, page or asset,
resolves relative to the directory of the page that links them. Inside raw HTML
a relative `href` or `src` value must be quoted: an unquoted relative raw-HTML
`href` or `src` value is refused. An unquoted absolute or `#fragment`-only value
is not refused. A link to a page or asset that is not in the built
site fails.

Pages under this repository's `docs/` are linked by GitHub URL, of the form
`https://github.com/joshua-stauffer/fitdocs/blob/main/docs/` followed by the
file. The build checks that the file exists in the repository and that any
`#anchor` matches a heading there.

### The annotation block

A page may end in an annotation block: the text from the last occurrence of an
empty line (no spaces), then `---`, then a line beginning `Annotations:`, to the
end of the file. Files use LF line endings. The build removes such a block and
leaves the rest of the page byte-for-byte unchanged, so it appears in no page,
search index or site index. A `---` rule that does not begin such a block is
kept.

The build recognises the block by those exact characters. A block in a CRLF body
after LF frontmatter, or one whose blank line before `---` holds spaces, is not
stripped and stays in the page.

## Building the site

The site tooling is a dependency group of this repository and is never part of
the installed package. Install it once, then build:

```
uv sync --group docs
uv run --group docs python -m scripts.build_site build
```

The tooling is pinned to `zensical==0.0.65`. A build writes the site to
`website/build/site/html/` and prints `built N pages into <root>/html`. That
directory is ignored by git. A failed build leaves no `html/` behind.

To build a content directory that lives outside the repository, pass it by
option or by variable:

```
uv run --group docs python -m scripts.build_site build --content ~/site-draft
FITDOCS_SITE_CONTENT=~/site-draft uv run --group docs python -m scripts.build_site build
```

To see whether the default content directory holds any included page, without
building:

```
uv run python -m scripts.build_site status
```

It prints `has_content=true` or `has_content=false` and does not need the
generator. It honours `--content` and `FITDOCS_SITE_CONTENT` as `build` does.

### The build root

`--build-dir` chooses the build root. Inside the repository a build root must be
under `website/build/`. The repository itself and its parent directories are
refused. A build root must never overlap the content directory: a root inside
it, equal to it, or containing it is refused. A root outside the repository is
allowed when it does not overlap the content directory.

### Failures and exit codes

When the build finds problems it prints one line per problem on standard error,
in the form `path: where: message`. A field that does not apply is left out.

- `path` is relative to the content directory. A problem in the site
  configuration template has the path `website/mkdocs.template.yml`, and a
  problem the site generator reports without naming a file has the path
  `site generator`.
- `where` is a frontmatter key, `hero_actions[N].href` for a hero link, a line
  number, a `line:col` position, or a dotted configuration key.

Pass `--verbose` to also print the generator's own output after those lines.

- `0` means success.
- `1` means the input has problems, listed as above.
- `2` means the command could not run: a missing content directory, a missing
  generator, a refused build root, an empty `--content`, or a preview process
  that exited by itself. A run refused before it builds or serves has written
  nothing. A preview whose serve process exits has already built into its
  preview root.

## Previewing the site

```
uv run --group docs python -m scripts.build_site serve
```

`serve` builds the site into `website/build/preview/` and serves it at
`127.0.0.1:8000`; `--addr HOST:PORT` changes the address. It accepts
`--content` and `FITDOCS_SITE_CONTENT` exactly as `build` does, so an out-of-repo
directory can be previewed while you edit it. When a file in the content
directory is created, changed or deleted, the preview rebuilds. A rebuild that
fails reports its problems in the same form as a build, keeps serving the
previous good site, and serves the change once it is fixed.

The preview's rebuild-on-save belongs to the repository's site tooling. fitdocs itself
performs no watching and no scheduling, and nothing in this page changes the
guarantees the rest of the documentation publishes about the installed tool.

## Maintainer runbook

The steps a maintainer does by hand. The pages themselves are the maintainer's
own copy; the tooling never writes them. Do steps 1 to 4 in this order: GitHub
documents verifying the domain first, then setting the custom domain, then
creating the DNS records. If the DNS records are created before the domain is verified and set as the
custom domain, someone else can publish a Pages site on the domain in the gap.

### 1. Verify the domain

In the GitHub account's own Settings (not the repository's), open Pages, choose
Add a domain and enter `fitdocs.ai`. Add the TXT record that GitHub shows, at
the name `_github-pages-challenge-<owner>` under the domain, where `<owner>` is
the GitHub account that owns the repository. Wait for the record to resolve,
which can take up to 24 hours, then choose Verify. Keep the record in place
afterwards, or the domain stops being verified.

### 2. Configure Pages

In the repository's Settings:

- Under Pages, set Source "GitHub Actions". The first deploy fails without it.
- Under Environments, limit the `github-pages` environment to deployment from
  the `main` branch.
- Under Pages, set the custom domain `fitdocs.ai`. A site published from Actions
  needs no `CNAME` file.

### 3. Add the DNS records

At the domain's DNS host, point the apex `fitdocs.ai` at GitHub Pages with four
A records and four AAAA records. The addresses are GitHub's documented apex
addresses, taken from docs.github.com ("Managing a custom domain for your GitHub
Pages site").

| Type | Address |
| --- | --- |
| A | `185.199.108.153` |
| A | `185.199.109.153` |
| A | `185.199.110.153` |
| A | `185.199.111.153` |
| AAAA | `2606:50c0:8000::153` |
| AAAA | `2606:50c0:8001::153` |
| AAAA | `2606:50c0:8002::153` |
| AAAA | `2606:50c0:8003::153` |

Add a `www` CNAME record pointing at `joshua-stauffer.github.io`.

### 4. Turn on Enforce HTTPS

Once the DNS records resolve, open the repository's Pages settings and turn on
Enforce HTTPS. GitHub offers it only after the records resolve, and it can take
up to 24 hours to become available.

### 5. Import the content

Copy the maintainer's pages into `website/content/` and build locally with the
command above. The annotation blocks may stay when the files use LF line
endings and the line before `---` is empty, because the build strips them. Land the change as any other change to
this repository, by commit. The site deploys only from `main`, and only when the
content directory holds an included page: a push to `main` then builds, checks
and deploys it.

### 6. Bump the Zensical pin

1. Edit the pin here, `zensical==0.0.65`, and in the `docs` group of
   `pyproject.toml`, then run `uv lock`.
2. Re-derive `ALLOWED_FEATURES` in `scripts/sitebuild/config.py` from the theme
   feature names the new release's bundle and templates reference, and update
   the test that pins it. The generator silently ignores a feature name it does
   not know, so the allowlist is the only check.
3. Re-verify the failure format: build a broken fixture and confirm the
   generator's problems still translate into one line each.
4. Run `FITDOCS_REQUIRE_SITE_TOOLING=1 uv run --group docs pytest tests/sitebuild`.
5. Read the release notes for changes to configuration keys.
