"""Regression tests for licence and format normalisation.

The whole point of collating is that one licence should have one name. The
index was carrying 308 datasets under "CC-BY-4.0" and 124 under "CC BY 4.0"
— the same licence, spelled two ways, so the API's `license` filter returned
one group and silently missed the other. These cases pin the collapse, and
just as importantly pin what must NOT collapse: a bespoke corporate licence
that happens to mention a version number is not Creative Commons.

No database or network needed, so CI runs it on every push.

Usage:  python scripts/licence_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from normalise import norm_license  # noqa: E402

failures: list[str] = []


def check(got, want, label: str) -> None:
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}"
          f"{'' if ok else f'  (got {got!r}, wanted {want!r})'}")
    if not ok:
        failures.append(label)


# --- one licence, one name ---------------------------------------------
for spelling in ("CC-BY-4.0", "CC BY 4.0", "cc by 4.0", "CC_BY_4.0",
                 "Creative Commons Attribution 4.0", "cc-by",
                 "Creative Commons Attribution",
                 "https://creativecommons.org/licenses/by/4.0/"):
    check(norm_license(spelling), "CC-BY-4.0", f"{spelling!r} is CC-BY-4.0")

for spelling in ("CC0", "CC0 1.0", "CC Zero", "cczero",
                 "Creative Commons CCZero", "Creative Commons Zero"):
    check(norm_license(spelling), "CC0-1.0", f"{spelling!r} is CC0-1.0")

# --- the canonical URLs, which are how half of them are recorded --------
# These match against a form with punctuation already flattened to spaces,
# so a pattern written with slashes and hyphens can never fire. One did,
# and by-sa URLs silently stopped resolving.
for url, want in (
        ("https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
        ("https://creativecommons.org/licenses/by-sa/4.0", "CC-BY-SA-4.0"),
        ("https://creativecommons.org/licenses/by-nc-sa/4.0/", "CC-BY-NC-SA-4.0"),
        ("http://creativecommons.org/licenses/by-nd/3.0", "CC-BY-ND-3.0"),
        ("https://creativecommons.org/publicdomain/zero/1.0/", "CC0-1.0")):
    check(norm_license(url), want, f"{url.split('.org')[1]} resolves")

# --- flavours are kept apart -------------------------------------------
check(norm_license("CC BY-SA 4.0"), "CC-BY-SA-4.0", "share-alike is its own licence")
check(norm_license("CC BY-NC-SA 4.0"), "CC-BY-NC-SA-4.0",
      "non-commercial share-alike is not share-alike")
check(norm_license("CC BY-ND 2.0"), "CC-BY-ND-2.0", "no-derivatives is not attribution")
check(norm_license("Creative Commons Attribution Share Alike 3.0"), "CC-BY-SA-3.0",
      "the long form resolves the same as the short")

# --- versions survive ---------------------------------------------------
check(norm_license("CC BY 3.0"), "CC-BY-3.0", "3.0 is not 4.0")
check(norm_license("CC BY 2.0"), "CC-BY-2.0", "2.0 is not 4.0")
check(norm_license("CC BY 2.5"), "CC-BY-2.5", "the .5 versions exist too")

# --- Open Government Licence -------------------------------------------
for spelling in ("OGL-UK-3.0", "Open Government Licence v3.0",
                 "open government license"):
    check(norm_license(spelling), "OGL-UK-3.0", f"{spelling!r} is OGL")

# --- what must NOT be swept up -----------------------------------------
# A bespoke licence is a real answer to "may I reuse this?" and turning it
# into a Creative Commons id would be inventing permission nobody granted.
for text in ("Cadent Gas Data Sharing Agreement",
             "Northern Powergrid Open Data Licence v1.0",
             "wpd-open-data", "OTHER-NC", "OTHER-CLOSED",
             "All Rights Reserved", "Zero Emission Vehicles",
             "accident report 4.0"):
    check(norm_license(text), text, f"{text[:34]!r} is left alone")

# A licence field mentioning Creative Commons in passing is not a grant of
# one. Asserting a licence nobody gave is the one mistake this field must
# not make, and a bare "by" matched anywhere used to make it.
for prose in ("Data published by the council; see creativecommons.org for details",
              "Creative Commons licences are used by some of our publishers"):
    # Assert what matters — that no CC identifier was invented — rather than
    # the exact passthrough text, which depends on the 60-character trim.
    check(str(norm_license(prose)).startswith("CC"), False,
          f"prose mentioning CC is not a licence grant: {prose[:40]!r}")

# ...but a note that actually states the licence still counts. This one is
# real, from seven datasets in the index.
check(norm_license("NB for Publisher: Use https://creativecommons.org/chooser/ "
                   "to create an appropriate sentence. The license selected is "
                   "CC-BY 4.0"), "CC-BY-4.0",
      "a messy note that names the licence is still that licence")

check(norm_license(None), None, "absent stays absent")
check(norm_license(""), None, "empty stays absent")
check(norm_license("   "), None, "whitespace stays absent")

# --- formats -------------------------------------------------------------
# norm_format() only passed through single tokens, so every multi-word label
# was dropped: 4,767 resources pointing at an ArcGIS REST service carried no
# format at all and the API's `format` filter could never find them.
from normalise import norm_format  # noqa: E402

for spelling in ("Esri REST", "ESRI REST", "GeoService",
                 "ArcGIS GeoServices REST API", "Esri Map Service"):
    check(norm_format(spelling), "ESRI-REST", f"{spelling!r} is one format")
check(norm_format("ARCGIS HUB DATASET"), "HTML",
      "a Hub portal page is a web page, not a service")
check(norm_format("Esri Shapefile"), "SHP", "multi-word shapefile resolves")
check(norm_format("Comma Separated Values"), "CSV", "spelled-out CSV resolves")
check(norm_format("CSV"), "CSV", "the plain token still works")
check(norm_format("NetCDF"), "NETCDF", "an unknown single token passes through")
check(norm_format("some unknown thing here"), None,
      "unknown multi-word text is not invented into a format")
check(norm_format(None), None, "absent format stays absent")

print()
print("all licence rules hold" if not failures
      else f"{len(failures)} failure(s): " + "; ".join(failures))
sys.exit(1 if failures else 0)
