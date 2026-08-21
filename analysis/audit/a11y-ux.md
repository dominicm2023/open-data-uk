# Accessibility & UX audit — public site

Axis: heading hierarchy, landmarks, form labels, chart/icon ARIA, keyboard, focus,
colour contrast of site chrome (computed, both themes), link text, tap targets,
colour-alone meaning, skip links, lang, reduced motion.
Sources: `web/index.html`, `web/about.html`, `web/dataset.html`, `web/site.css`,
`pagerender.py`, `charts.py`, `index.db`, plus 8 live fetches (project UA, ≤1 req/s).
Ranked by user harm.

---

## F1 — HIGH · Long tag chips force full-page horizontal scroll (WCAG 1.4.10 Reflow, AA)

`.chip { white-space: nowrap }` (`web/site.css:241-247`) and the dataset renderer
emits publisher tags as chips with no length cap (`pagerender.py:339-340` — caps
*count* at 20, not length). The index holds **341 distinct tags longer than 45
characters**; the worst is **1,132 characters** (query:
`SELECT tag, length(tag) FROM dataset_tags GROUP BY tag ORDER BY 2 DESC LIMIT 1`
→ 1132, on `spatialdata_scot:1577d05b-36f2-4c4d-b2a1-9de3de2d4809`).

Live-confirmed: `https://open-data.org.uk/dataset?key=spatialdata_scot%3A1577d05b-36f2-4c4d-b2a1-9de3de2d4809`
(HTTP 200) renders that 1,132-char string as a single `class="chip tag"` link —
an unbreakable element roughly 7,000px wide. The whole page scrolls sideways on
every viewport; on a phone the content is unreadable. The `/topic?tag=…` link it
points at also puts the full string in the `<h1>` and `<title>`. Affects every
dataset page carrying one of these tags. Fix shape: `_fit`-style truncation or
`overflow-wrap:anywhere` on `.chip.tag`, and arguably these comma-joined blobs
are un-split tag lists that `norm_tag` could split upstream.

## F2 — HIGH · No skip link anywhere; no `<main>` landmark on ~all pages (WCAG 2.4.1 A, 1.3.1)

No page has a skip link. Only `web/index.html:63` has `<main>`; the template every
server-rendered page uses puts content in a bare `<div class="wrap wide">`
(`web/dataset.html:39-41`), and `web/about.html:47` likewise. Live check: on
`https://open-data.org.uk/publishers` the only landmark-ish element in the body is
`<nav>` (grep of fetched page: 1 × `<nav`, 0 × `<main`, 0 × "skip"). Keyboard users
tab through brand + 7 nav links on every one of ~60k pages with no bypass; screen
reader users have no main landmark on dataset/browse/findings pages — i.e. on
everything except the home page. One template edit fixes the entire site.

## F3 — MED · Search results live region announces (or swallows) the entire result list (WCAG 4.1.3)

`web/index.html:72` — `<div id="out" aria-live="polite">` — then `render()` writes
the banner plus up to 15 full result cards into it via innerHTML
(`web/index.html:150-174`), after an intermediate "Searching…" write (line 187).
Replacing a live region's whole subtree makes screen readers either read out the
entire 15-card dump or announce nothing reliably, varying by engine. Better: keep
`#out` non-live and announce a short status ("15 results for …", "No results") in
a separate `role="status"` element.

## F4 — MED · "Open at publisher ↗" is a dead `href="#"` link on 536 datasets

`pagerender.py:354` always renders the primary CTA; `safe_url()`
(`pagerender.py:64-67`) returns `"#"` for missing/non-http landing URLs. Query:
`SELECT COUNT(*) FROM datasets WHERE landing_url IS NULL OR landing_url='' OR
(landing_url NOT LIKE 'http://%' AND landing_url NOT LIKE 'https://%')` → **536**
of 106,609. On those pages the most prominent control silently scrolls to top —
for a screen reader it's an unlabelled-destination link (2.4.4); for everyone it's
a broken promise. Same pattern exists client-side (`web/index.html:91,163`) for
result titles. Fix shape: render plain text ("publisher gives no link") when
`safe_url` yields `#`.

## F5 — MED · Mobile nav scroller hides its own existence

`web/site.css:147-158`: below 40rem the 7-item nav becomes one non-wrapping row
with `overflow-x:auto` and the scrollbar explicitly hidden
(`scrollbar-width:none`, `::-webkit-scrollbar{display:none}`). On a 320–375px
phone the tail items (Findings, About, API) sit off-screen with no scrollbar, no
fade, no cue that more exist. Reachable by keyboard/AT (links are focusable), so
not a WCAG failure — but a discoverability hole for exactly the pages the project
wants found. Add a fade/gradient edge or let it wrap to two rows.

## F6 — LOW-MED · Search input: designed focus outline is dead code; border is the only boundary at 1.55:1 (WCAG 2.4.7, 1.4.11)

`web/site.css:82-86` gives `input:focus-visible` a 2px accent outline, but
`input[type=search] { outline: none; }` (`site.css:199-209`) has equal
specificity (0,1,1) and comes later, so it wins and the outline never renders.
What remains is the 1.5px border colour change to accent (`site.css:210`) — a
visible indicator (passes 2.4.7) but far weaker than every other control's.
Separately, the input's resting boundary is `--line-strong` on `--card`:
**1.55:1 light, 1.62:1 dark** (computed), below the 3:1 of 1.4.11 for component
boundaries — mitigated only by the placeholder text inside it. Reordering the
rules (or `outline: none` → only on `:focus:not(:focus-visible)`) fixes the first;
a darker border the second.

## F7 — LOW-MED · Public "API" nav item lands on Swagger UI with no `lang` attribute (WCAG 3.1.1 A)

Live: `https://open-data.org.uk/docs` serves FastAPI's stock Swagger page —
`<html>` with **no lang attribute** (observed in response), all UI from a CDN
bundle, with Swagger UI's known keyboard/contrast rough edges. It's the only
public page failing 3.1.1. Cheap improvement: a hand-written `/docs` landing page
in site chrome (the About page already lists the three endpoints), or FastAPI's
`docs_url` swapped for a custom page that sets `lang`.

## F8 — LOW · No `aria-current` on any server-rendered page's nav

`web/dataset.html:28-36` hard-codes the nav with no `aria-current`; live pages
`/publishers`, `/topics`, `/findings`, `/who-publishes`, `/dataset?…` all contain
zero occurrences (grep of fetched HTML). `index.html:47` and `about.html:42` do
set it, so Publishers/Subjects/Findings visitors get no "you are here" in the nav
while Search/About visitors do. (2.4.8 is AAA; this is mainly consistency.)
Needs the template to take a current-page slot.

## F9 — LOW · New-tab behaviour is unannounced and inconsistent

Search result titles open `target="_blank"` (`web/index.html:163`) with no
"opens in new tab" indication, visual or programmatic; the equivalent links on a
dataset page (`pagerender.py:314,354`) open in the same tab. Advisory (G200) —
pick one behaviour, and if `_blank` stays, append a visually-hidden
"(opens in new tab)".

## F10 — LOW · Geo banner ends in a call to action with nothing to click

`web/index.html:127`: "Know a {place} data source? Suggest it!" — plain text, no
link. The suggestion route exists (`/about#…`, GitHub). A user moved to act is
dropped at the moment of highest intent.

## F11 — LOW · Home page heading jump h1 → h3

Result cards use `<h3>` (`web/index.html:163`) directly under the page `<h1>`;
no h2 exists. Screen-reader heading navigation implies a missing level. Cosmetic
fix: h2, styled as now.

## F12 — INFO · Duplicate `id="hatch"` ×8 on /findings

Every chart SVG defines its own `<pattern id="hatch">` (`charts.py:196-200`);
the live findings page contains 8 of them (grep of fetched page). All references
resolve to the first, and the patterns are identical, so rendering is correct —
it's an HTML-validity wart (4.1.1 is obsolete in WCAG 2.2). Suffix the id per
chart if it ever varies.

## F13 — INFO · `autofocus` on the search box (`web/index.html:68`)

Defensible for a search-first page (Google does it), but it skips screen-reader
users past the header on load and pops the keyboard on some mobile browsers.
Noting, not urging.

---

## Where nothing is wrong (checked, not skipped)

- **Site chrome contrast, both themes — clean.** Computed every text/ground pair
  from `site.css` tokens: light `--muted` on `--bg` 5.45:1, on `--card` 5.85:1;
  `--accent` on card 7.56:1; nav-current accent-on-soft 6.57:1; button white on
  accent 7.56:1; chips `--ok` 6.56, `--warn` 7.63, `--amber` 6.25 on card. Dark:
  muted 6.29–6.92, accent 7.64–8.41, chips 6.73–9.02, button ink-on-accent 8.25.
  Every text pair ≥4.5:1 at its size; most clear AAA. The one sub-3:1 non-text
  element is the search input border (F6).
- **Findings SVGs are wired correctly.** Live `/findings`: every chart carries
  `role="img"` + `aria-label` matching its `<title>`, plus a `<desc>`
  (`charts.py:189-201`). The brand icon is `aria-hidden="true"` everywhere.
- **Availability chips never rely on colour alone.** Every state pairs colour
  with a distinct symbol + words (`web/index.html:142-149`, `pagerender.py:34-41`),
  and charts hatch "dead" instead of merely recolouring (`charts.py`
  `unit_grid`/`hbar`, `--hatch-dead` in `site.css:413`).
- **Form labelling is right.** The search box has a visually-hidden `<label
  for="q">` and an `aria-label` (`web/index.html:65-66`) — redundant but valid.
- **No keyboard traps.** No modals, no key handlers, no positive tabindex
  anywhere in `web/` or rendered output.
- **`lang="en-GB"`** on every page except `/docs` (F7) — verified on 7 live pages.
- **Reduced motion respected**: the only transitions are gated behind
  `prefers-reduced-motion: no-preference` (`site.css:368-370`); nothing else moves.
- **Focus visibility** is strong (2px offset accent outline, 7.05–8.41:1 against
  both grounds) on links and buttons — the search input excepted (F6).
- **No "click here"** anywhere; link text is generally excellent. Repeated
  "details →" per result card is contextualised by its sibling heading (passes
  2.4.4 AA).
- **Tap targets** pass WCAG 2.2's 24px minimum: mobile nav links ≈29px tall,
  letter links ≈29px; tag chips ≈23px tall but with ≥24px centre-to-centre
  spacing (the 2.5.8 spacing exception). Below the 44px best-practice bar, none
  below the normative one.
- **404 behaves**: `/dataset?key=no-such-key` returns a real HTTP 404 with an
  explanatory page and a route back (`pagerender.py:658-667`).
- **Zoom/reflow chrome**: viewport meta doesn't lock zoom; wide tables scroll in
  their own box (`site.css:307`); charts scroll in `figure` below a 34rem floor
  (`site.css:488-492`). The one reflow break is F1.
