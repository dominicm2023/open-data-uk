"""Check that chart text fits the box it is drawn in.

SVG does not reflow. Text that is too wide does not wrap or shrink — it is
simply drawn over whatever is next to it, and the chart still validates as
XML and still renders. So nothing catches a collision except a check that
measures the geometry, which is what this does.

The bugs this exists to prevent, both of which shipped:

  * `hbar` cut labels at 34 characters and left-aligned them in a 204px
    gutter. At 14px that is about 248px of text, so every long council name
    was printed across its own bar.
  * `share_bar` placed its unit label beside the big number at an x
    position derived from how many digits the number had, which put "state
    no licence" through the middle of "34%".

Captions are the other recurring risk: they come from findings.json, so
their length is whatever the finding happens to say that night.

Run against the real findings, plus deliberately hostile strings.

Usage:
    python scripts/charts_test.py
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import charts  # noqa: E402

ROOT = Path(__file__).parent.parent
SVG_NS = "{http://www.w3.org/2000/svg}"
FAILURES: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        FAILURES.append(label)


def _texts(svg: str) -> list[dict]:
    """Every text element with its position, class and estimated extent."""
    root = ET.fromstring(svg)
    out = []
    for el in root.iter(f"{SVG_NS}text"):
        cls = el.get("class", "")
        # Sizes and width factors come from charts.py, not a copy of them:
        # a test carrying its own estimates would agree with a wrong drawing.
        size = charts.SIZE_BY_CLASS.get(cls, 14)
        text = el.text or ""
        width = charts._w(text, size, cls)
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        anchor = el.get("text-anchor", "start")
        left = x - width if anchor == "end" else x
        # y is the baseline. The em box reaches roughly 0.8em above it and
        # 0.22em below, and it is the box that collides — a 62px number sat
        # 7.6px into the label under it and only looked fine because digits
        # happen to have no descenders.
        out.append({"cls": cls, "text": text, "x": x, "y": y,
                    "left": left, "right": left + width, "size": size,
                    "top": y - size * 0.80, "bottom": y + size * 0.22})
    return out


def _rects(svg: str) -> list[dict]:
    root = ET.fromstring(svg)
    out = []
    for el in root.iter(f"{SVG_NS}rect"):
        out.append({"x": float(el.get("x", 0)), "y": float(el.get("y", 0)),
                    "w": float(el.get("width", 0)),
                    "h": float(el.get("height", 0)),
                    "fill": el.get("fill", "")})
    return out


def check_svg(svg: str, name: str) -> None:
    view = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    width, height = int(view.group(1)), int(view.group(2))
    texts = _texts(svg)

    over = [t for t in texts if t["right"] > width - 6]
    check(not over, f"{name}: no text runs past the right edge"
          + (f" — {over[0]['cls']} {over[0]['text'][:34]!r} ends at "
             f"{over[0]['right']:.0f} of {width}" if over else ""))

    below = [t for t in texts if t["y"] > height - 2]
    check(not below, f"{name}: no text below the bottom edge"
          + (f" — {below[0]['text'][:34]!r} at y={below[0]['y']}" if below else ""))

    # A label must not cross a data bar on its own row. Bars are the coloured
    # rects; the tinted provenance band and the full-width track are not.
    bars = [r for r in _rects(svg)
            if r["w"] < width - 40 and r["h"] < 40 and r["x"] > 0]
    clashes = []
    for t in texts:
        if t["cls"] not in ("t-label", "t-unit"):
            continue
        for b in bars:
            same_row = b["y"] <= t["y"] <= b["y"] + b["h"] + 6
            if same_row and t["right"] > b["x"] + 1 and t["left"] < b["x"]:
                clashes.append((t["text"][:30], b["x"]))
    check(not clashes, f"{name}: no label crosses a bar"
          + (f" — {clashes[0][0]!r} reaches bar at x={clashes[0][1]:.0f}"
             if clashes else ""))

    # No two runs of text may share space, in either direction. Checking rows
    # alone missed the number-over-caption case entirely, because those two
    # sit on different baselines.
    overlaps = []
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if (a["right"] > b["left"] + 1 and b["right"] > a["left"] + 1
                    and a["bottom"] > b["top"] + 1 and b["bottom"] > a["top"] + 1):
                overlaps.append((a["text"][:24], b["text"][:24]))
    check(not overlaps, f"{name}: no two runs of text share space"
          + (f" — {overlaps[0][0]!r} into {overlaps[0][1]!r}" if overlaps else ""))


def _lum(hexcode: str) -> float:
    hexcode = hexcode.lstrip("#")
    parts = [int(hexcode[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
           for c in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def check_label_contrast() -> None:
    """Text drawn on a filled shape must be readable on it.

    This is the third contrast fault in the project and the second of exactly
    this shape: a token that is right against the page background and wrong
    against a coloured fill. The treemap wrote its labels in --ink on every
    tile of a pale-to-saturated ramp, which measured 2.35:1 on the darkest
    tile in light mode and 1.83:1 in dark.
    """
    ramps = {
        "index light": (["#dce8f6", "#abc6e6", "#7099cb", "#3d72ad", "#14549c"],
                        ["#16181c", "#16181c", "#16181c", "#ffffff", "#ffffff"]),
        "index dark": (["#24384f", "#31517a", "#3f6899", "#5f91cc", "#7ab3ee"],
                       ["#e9eaec", "#e9eaec", "#e9eaec", "#16181c", "#16181c"]),
        "joined up light": (["#d9efe9", "#a3d6c9", "#66b3a2", "#2b7867", "#0e6e63"],
                            ["#16181c", "#16181c", "#16181c", "#ffffff", "#ffffff"]),
        "joined up dark": (["#17352f", "#215048", "#2f7264", "#459a87", "#5ecdb6"],
                           ["#e9eaec", "#e9eaec", "#e9eaec", "#16181c", "#16181c"]),
    }
    for name, (fills, inks) in ramps.items():
        worst = min(contrast(ink, fill) for ink, fill in zip(inks, fills))
        check(worst >= 4.5,
              f"{name}: every ramp step carries readable label text "
              f"(worst {worst:.2f}:1)")


def check_the_checker() -> None:
    """Prove the geometry checks can fail.

    A collision detector that passes everything is indistinguishable from one
    that isn't looking, so this feeds it the exact layout that shipped broken
    — a 34-character label, left-aligned at x=28, against bars starting at
    x=232 — and asserts it complains.
    """
    global FAILURES
    broken = (
        '<svg viewBox="0 0 720 120" xmlns="http://www.w3.org/2000/svg">'
        '<text x="28" y="47" class="t-label">'
        'Bath and North East Somerset CCG X</text>'
        '<rect x="232" y="34" width="300" height="17" fill="#14549c"/>'
        '<text x="700" y="47" class="t-value">1,234</text></svg>')
    kept, FAILURES = FAILURES, []
    check_svg(broken, "self-check/horizontal")
    horizontal = len(FAILURES)

    # And the vertical case: a 62px number with a caption tucked 24px under
    # its baseline, which is the spacing that shipped.
    stacked = (
        '<svg viewBox="0 0 720 200" xmlns="http://www.w3.org/2000/svg">'
        '<text x="28" y="90" class="t-big">34%</text>'
        '<text x="28" y="114" class="t-unit">state no licence</text></svg>')
    FAILURES = []
    check_svg(stacked, "self-check/vertical")
    vertical = len(FAILURES)
    FAILURES = kept

    check(horizontal >= 2,
          f"the checks catch a label drawn through a bar ({horizontal} fired)")
    check(vertical >= 1,
          f"the checks catch text stacked too close ({vertical} fired)")


def main() -> int:
    print("--- label text on coloured fills")
    check_label_contrast()

    print()
    print("--- can these checks fail?")
    check_the_checker()
    print()
    path = ROOT / "findings.json"
    if not path.exists():
        print("findings.json not found — run scripts/findings.py first")
        return 1
    findings = json.loads(path.read_text(encoding="utf-8"))

    print("--- the findings as published")
    drawn = 0
    for f in findings:
        svg = charts.render(f, measured="17 August 2026")
        if not svg:
            continue
        drawn += 1
        check_svg(svg, f"{f['kind']}/{f['headline'][:30]}")
    check(drawn > 0, f"{drawn} findings drew a chart")

    print("\n--- deliberately hostile text")
    long_name = "Bath and North East Somerset Clinical Commissioning Group"
    hostile = [
        {"kind": "link-rot", "headline": "long publisher names",
         "sql": "SELECT " + "x" * 300, "link": "https://open-data.org.uk",
         "numbers": {"others": [{"publisher": long_name, "dead": 1234},
                                {"publisher": "A", "dead": 1}]}},
        {"kind": "coverage", "headline": "long nation caption",
         "sql": "council_coverage.json", "link": "https://open-data.org.uk",
         "numbers": {"nation": "Yorkshire and the Humber Combined Authority Area",
                     "no_trace": 97, "published_centrally": 3, "councils": 100}},
        {"kind": "licensing", "headline": "big denominator",
         "sql": "SELECT COUNT(*) FROM datasets WHERE license_norm IS NULL",
         "link": "https://open-data.org.uk",
         "numbers": {"no_licence": 999999, "datasets": 1000000}},
    ]
    for f in hostile:
        svg = charts.render(f, measured="17 August 2026")
        check(bool(svg), f"{f['headline']}: drew at all")
        if svg:
            check_svg(svg, f["headline"])

    print("\n--- a finding whose numbers don't fit its chart")
    broken_shape = {"kind": "coverage", "headline": "renamed field",
                    "sql": "x", "link": "https://open-data.org.uk",
                    "numbers": {"nation": "England", "renamed": 5}}
    check(charts.render(broken_shape) == "",
          "a missing number yields no chart rather than an exception")

    print("\n--- comparison forms with hostile data")
    crowded = [(f"Authority {i}", 100 + i * 0.4, 90 + (i % 7) * 0.3)
               for i in range(18)]
    body, height = charts.slope(crowded, "2013-14", "2024-25",
                                "eighteen near-identical values fight for "
                                "label space", highlight={"Authority 3"})
    check(bool(body), "slope draws 18 crowded pairs")
    check_svg(f'<svg viewBox="0 0 720 {height}" '
              f'xmlns="http://www.w3.org/2000/svg">{body}</svg>',
              "slope/crowded")
    spread_pts = [{"x": i % 5, "y": (i * 37) % 11,
                   "label": f"Long Authority Name {i}" if i % 3 == 0 else None}
                  for i in range(40)]
    body, height = charts.scatter(spread_pts, "score", "per head",
                                  "forty points, a third labelled", rho=-0.03)
    check(bool(body), "scatter draws 40 points with labels")
    check_svg(f'<svg viewBox="0 0 720 {height}" '
              f'xmlns="http://www.w3.org/2000/svg">{body}</svg>',
              "scatter/crowded")

    print("\n--- a signed Joined Up graphic")
    svg = charts.render(findings[0], byline="Dominic Matthews",
                        measured="17 August 2026")
    check("ARGUMENT BY" in svg, "a byline replaces the unsigned query label")
    check("HOW IT WAS MEASURED" not in svg,
          "an argument is not labelled as a measurement")
    check_svg(svg, "signed")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} chart geometry rule(s) broken")
        return 1
    print("all chart geometry rules hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
