# fitdocs.ai docs: design handoff

These changes come from a design pass on the fitdocs.ai docs site (Zensical, with `brand.css` overrides).
The mockups used stand-in class names (`.typeset`, `.fd-nav`, `.fd-toc`, `.fd-btn`). **Map each rule onto the
real Zensical/Material selectors in this repo. Check them against the built site's DOM.** Likely matches:

| Mock class | Likely real selector |
|---|---|
| `.typeset` | `.md-typeset` |
| `.fd-nav` (left nav) | `.md-sidebar--primary .md-nav` |
| `.fd-nav-label` (group heading) | `.md-nav__item--section > .md-nav__link`, or `.md-nav__title` |
| `.fd-toc` (right TOC) | `.md-sidebar--secondary .md-nav` |
| `.fd-btn`, `.fd-btn-primary` | `.md-button`, `.md-button--primary` |
| `.fd-main` | `.md-content__inner` |
| page max-width | `.md-grid` |

Change CSS only. No markdown content changes are needed, except for the hero (section 5).

## 1. Readability (all pages)

The goal is less overwhelming, text-heavy pages. The rules use these tokens:

```css
:root {
  --fd-text: 17px;      /* body size (was 16) */
  --fd-leading: 1.7;    /* line-height (was 1.6) */
  --fd-measure: 70ch;   /* max line length of the article */
}
```

- **Layout:** set the page grid max-width to 1360px (was 1220). Set both sidebars to 256px. Set content padding to `56px 64px 120px`, and `32px 20px 72px` below 960px. Hide the TOC below 1280px.
- **Article:** apply `max-width: var(--fd-measure); margin: 0 auto; font-size: var(--fd-text); line-height: var(--fd-leading)`.
- **Spacing:** paragraphs and lists get `margin: 0 0 1.25em` (space below only). List items get `margin-bottom: .6em`. Lists get `padding-left: 1.4em`.
- **Headings:** use weight 650 (was 300/400) in the strongest text color.
  - `h1`: 2.25em, line-height 1.15, letter-spacing −0.022em, margin `0 0 .5em`.
  - First paragraph after the `h1`: 1.15em, as a lede.
  - `h2`: 1.5em, margin `2.25em 0 .6em`, `padding-top: 1.25em`, 1px top border. An `h2` directly after an `hr` gets no border.
  - `h3`: 1.15em, margin `2em 0 .5em`. An `h3` directly after an `h2` gets `margin-top: 1em`.
- **Body links:** underline 1px, with offset .22em and the accent color at 40% opacity (`color-mix`). On hover, the underline is full accent.
- **Inline code:** .86em, padding `.12em .38em`, radius 4px.
- **Code blocks:** margin `1.5em 0 1.75em`, padding `1.1em 1.4em`, 1px border, radius 8px, line-height 1.65.
- **Tables:**
  - Wrapper: 1px border, radius 8px, `overflow-x: auto`.
  - Table: font .9em, line-height 1.55, width 100%.
  - `th`: .78em uppercase, letter-spacing .05em, muted color, code-background fill.
  - `td`: padding `.9em 1.2em`, hairline top border. Use `td code { white-space: nowrap }`.
- **`hr`:** margin 2.5em.
- **Left nav:**
  - Group headings: 11.5px, weight 700, uppercase, letter-spacing .08em.
  - Links: `padding: 5px 10px; border-radius: 6px`, with a subtle hover background. The current page gets weight 600, the hover background, and the accent color.
  - Groups are 28px apart. Line-height is 1.45.
- **TOC:** title "On this page", styled like the nav group headings. The list gets a 1px left rail. Links get `padding: 4px 0 4px 14px`. The active item gets the accent color and a 2px accent left border.

### Light tokens

```css
--fd-fg: rgba(0,0,0,.80);         /* body */
--fd-fg-strong: rgba(0,0,0,.90);  /* headings, strong */
--fd-fg-light: rgba(0,0,0,.58);   /* muted, ≥4.5:1 */
--fd-fg-lighter: rgba(0,0,0,.45);
--fd-border: rgba(0,0,0,.08);
--fd-border-strong: rgba(0,0,0,.12);
--fd-hover-bg: rgba(0,0,0,.045);
--fd-code-bg: #f6f7f8;
```

## 2. Dark mode fixes (slate scheme)

```css
--fd-fg: hsla(225,15%,90%,.80);
--fd-fg-strong: hsla(225,15%,96%,.95);
--fd-fg-light: hsla(225,15%,90%,.60);
--fd-fg-lighter: hsla(225,15%,90%,.42);
--fd-border: hsla(225,15%,95%,.10);
--fd-border-strong: hsla(225,15%,95%,.16);
--fd-hover-bg: hsla(225,15%,95%,.06);
--fd-nav-label: hsla(225,15%,97%,.96);  /* nav group headings: bright */
--fd-nav-link: hsla(225,15%,90%,.66);   /* nav links: dimmer than headings */
--fd-btn-fg: hsla(225,15%,92%,.90);     /* outline buttons: was header graphite, invisible */
--fd-on-accent: hsla(225,20%,10%,1);    /* text on accent fill: dark, since white on #f07d8e fails contrast */
```

- **Nav headings vs. links:** headings use `--fd-nav-label` and links use `--fd-nav-link`. Before, they had nearly the same brightness.
- **Hero buttons:**
  - Outline buttons: text and border use `--fd-btn-fg`.
  - Primary buttons: text uses `--fd-on-accent`.
  - Hover: text uses `--fd-on-accent`.
- **Light mode:** these four tokens fall back to the light values (`--fd-fg-light`, `--fd-fg`, `--fd-primary`, `#fff`).

## 3. Accent

The accent stays `#b8324b` (light) and `#f07d8e` (dark). A candidate brand red, taken from the route line on workout maps, is `#a3203a`. It hasn't been adopted.

## 4. Design language (optional, for later)

These are taken from what fitdocs already outputs:

- **Data colors:** heart rate `#d5455f`, power `#cd6600`, elevation `#8a8f98` at 18%. HR zones Z1–Z5: `#2f8adc #32b36e #d5bf36 #e87f25 #e64343`.
- **Numbers:** monospace, tabular, right-aligned. Prose stays in the system sans font.
- **Possible components for guides:**
  - stat strip (label in small caps above a mono value)
  - file chip (`athlete.toml` with a document icon)
  - figure card with caption
  - zone bar
  - key–value table with mono values
  - status pills for detected / not detected / not assessed

## 5. Hero

- **Images:** add `fitdocs-hero.webp` (2400×1350) to the docs assets, and keep `fitdocs-hero@2x.png` as a fallback.
- **Placement:** it replaces the current synthetic demo chart in the home page hero card.
- **Hero text:** set it in `index.md` frontmatter (`hero_title`, `hero_tagline`, `hero_actions`). It is not part of the image.
- **Duplicate headline:** the page's own `# h1` currently repeats the hero title. Keep only one of them.
- **Alt text:** "Example fitdocs workout page: summary stats, route map, heart-rate and power chart, and notes".
- **Background:** the image includes a light grey (#eceef1) background, so it shows as a light panel in dark mode.
- **Data:** the image shows real data from the Valencia Marathon, 2024-12-01. The notes text is illustrative. Map tiles are © OpenStreetMap contributors, and that credit is inside the image.
