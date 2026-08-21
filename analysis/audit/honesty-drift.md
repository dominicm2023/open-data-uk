# Honesty-drift audit — the site's claims vs the index

Measured 2026-08-21 against the **local** `index.db` (file dated 17 Aug — lags prod by ~4 days,
and predates the 20 Aug checker fix that stopped counting HTTP 400/409/418 as dead, so every
"dead" percentage below is a **ceiling** for prod). Whole catalogue = all 106,609 rows of
`datasets`; findable = minus `duplicates` (21,144) and `retired` (1,064) = 84,486.

## The table, ranked by how bad it looks to a sceptical reader

| # | Claim | Where stated | Current value (local db, 17 Aug) | Verdict |
|---|-------|--------------|----------------------------------|---------|
| 1 | "We check **every link** first" / "with **every link verified**" | web/index.html:7 (meta description), :12 (og:description) | 74.2% of the catalogue has been followed (79,065 of 106,609 have non-null `availability`); About:71 itself says 73% | **wrong** — home page overclaims, and contradicts our own About page |
| 2 | "1,400-odd government bodies, councils, NHS organisations and agencies" | web/about.html:143 (link to /publishers) | 1,799 distinct publishers on the findable set — the exact count the /publishers page renders (server.py:521-533) | **wrong** — off by ~400 (28%); anyone counting the publishers page sees it |
| 3 | Of stale datasets that declare an update schedule, "**70% say they were never going to be updated again**" | web/about.html:85-87 | 46.9% notPlanned over the whole catalogue (3,161 of 6,741); 51.6% over findable (2,402 of 4,657). Reaches ~70% only if "asneeded" (17.6%) is counted as "never again", which the sentence does not support | **wrong** — 18-23 point drift; also undercuts the "though most were never meant to be" aside at about.html:68 (only 15% of stale datasets declare any schedule at all) |
| 4 | "**10% are genuinely broken**" (of checked links) | web/about.html:77 | 7.0% dead (5,534 of 79,065 checked) — and this predates the 20 Aug 400/409/418 reclassification, so prod is lower still | **drifted** (3 pts, overstating brokenness; will widen) |
| 5 | "For **15%** the publisher lists no files at all" | web/about.html:76-77 | 18.1% nofiles (14,345 of 79,065) | **drifted** (3.1 pts) |
| 6 | "the **82,000-odd** datasets you can actually find through search" | web/about.html:100 | 84,486 findable locally; the live /findings page's own basis (findings.json:8) says 84,494 | **drifted** — ~2,500 low, two of our own pages disagree, and growth widens it |
| 7 | "hundreds of spellings of file formats and **dozens of licence variants** collapse to a consistent vocabulary" | web/about.html:79-81 | 1,239 distinct raw licence spellings vs 391 raw format spellings — licences out-vary formats 3:1, and even `license_norm` has 752 distinct values | **wrong** — the sentence has the two magnitudes backwards |
| 8 | Wales coverage card: "A further **8** in Wales appear only inside another publisher's records" (centrally list includes Neath Port Talbot) | findings.json:146-161 → rendered on /findings | Fresh run of the same code gives **7**: Neath Port Talbot moved from state `none` to `filtered` in council_coverage.json after findings.json was generated | **drifted** (minor, but it is a named-council claim) |
| 9 | "37% give you machine-readable data — 13% a direct file, 24% an API" | web/about.html:73-74; also about.html:7 meta ("only 37% of verified links…") | 35.4% (data 12.1% + api 23.3%) | fresh-ish — inside the 2-pt line per component, but the headline 37% is 1.6 pts high and drifting down |
| 10 | "Another 30% just lead to a webpage" | web/about.html:74-75 | 28.4% | fresh (1.6 pts) |
| 11 | "10% we couldn't check because the publisher blocked us" | web/about.html:78 | 11.1% blocked | fresh (1.1 pts) |
| 12 | "37% state no licence" (whole catalogue) | web/about.html:67, :7 | 37.2% (39,618 of 106,609) | **fresh** |
| 13 | "42% haven't been updated in over two years" | web/about.html:68 | 41.9% of all rows (42.9% of the 104,137 with a parseable date) | **fresh** |
| 14 | "19% are duplicate copies" | web/about.html:69 | 19.8% (21,144 of 106,609) | **fresh** (0.8 pts, creeping toward the line) |
| 15 | "We've followed the links on 73% of the catalogue … still catching up" | web/about.html:71-73 | 74.2% | **fresh**, and moving the direction the caveat promises |
| 16 | "licensing is better (34% state none)" among findable | web/about.html:102 | 33.6% (28,357 of 84,486) | **fresh** |
| 17 | /findings tier-1/2 figures: 34% no licence (84,494 / 28,360); abolished councils 1,136 / 1,072 checked / 260 dead / 24%; dead hosts 2,909 links / 28 hosts / 132 publishers; misoportal 904 / 100 councils; "Conservation Areas" 98 bodies / 38 licences / 13 unlicensed; England 5/296 and Scotland 1/32 no-trace | findings.json (rendered by pagerender.py:670) | Fresh re-run of scripts/findings.py analyses (read-only, same SQL) reproduces every number: 84,486/28,357→34%; 260/1,072→24%; identical dead-host and licence-disagreement figures; England 5/296, Scotland 1/32 | **fresh** (see caveat below on dead-based figures) |
| 18 | COUNCIL_COVERAGE.md headline: "331 of 361 councils (92%) have data … only 103 (29%) run a portal we harvest" | COUNCIL_COVERAGE.md:5 | council_coverage.json: 361 councils, 30 state `none` → 331 with data (91.7%); 103 state `own` (28.5%) | **fresh** |
| 19 | "rate limit (30 searches/minute)" | web/about.html:175-176 | server.py:41-42 `RATE_LIMIT = 30`, `RATE_WINDOW = 60` | **fresh** |
| 20 | Privacy: "we log the search text … not your IP, browser, or any cookie/session identifier" | web/about.html:180-184 | querylog.py:31-40 — `queries` table columns are ts, query, k, confidence, top_similarity, n_results, place, bbox_matches, top_key; no IP/UA/session anywhere | **fresh** — verified true in code |

## Places two of our own pages disagree

1. **index.html:7,12 vs about.html:71** — "every link verified" vs "73% followed". The About page is honest; the home page's metadata (what Google shows) is not. Worst single item in this audit.
2. **about.html:100 ("82,000-odd") vs findings.json:8 (84,494)** — the About page and the /findings page quote different findable totals.
3. **findings.json:146 (Wales "further 8") vs council_coverage.json** — fresh run says 7; Neath Port Talbot changed state since generation.
4. **COUNCIL_COVERAGE.md internal** — the summary table (line 7-12) has no column for the 🟠 `filtered` state, so England sums to 295 of its 296 councils and Wales to 21 of 22, while 🟠 appears unexplained against Rochdale (line 215) and Neath Port Talbot (line 387). Cosmetic, but a careful reader can't make the rows add up.

## Caveats

- Every figure above is from the local index.db dated **17 Aug**; prod is ~4 days ahead. For the fresh verdicts the drift over 4 days is well under a point; for the flagged ones the gap is far larger than any 4-day movement.
- The 20 Aug checker fix (400/409/418 no longer "dead") postdates this DB copy. All dead-derived numbers — the About "10% broken" (already 3 pts high), the abolished-councils 260/24%, and the MMO 87% link-rot figure — should be regenerated on prod after the next checker sweep; they can only go down.
- "The whole index rebuilds … in about an hour" (about.html:170) and "index grew by a third recently" (about.html:71) are not verifiable from the local copy; not scored.
- Hub pages (/publishers, /topics, /who-publishes) carry **no static figures** — everything is computed live in server.py `_aggregates()` — so there is nothing on them to drift. A genuine "nothing wrong here".
