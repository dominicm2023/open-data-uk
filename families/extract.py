"""Bounded extraction of one fetched file into tables. Subprocess; no network.

Derived from Codex's pilot extractor (September 2026), with two formats
added: an ArcGIS REST query result and GeoJSON, both of which arrive as
features rather than rows and are flattened here so every family adapter
sees the same shape — a header row followed by value rows. Geometry becomes
`_lon`/`_lat` columns (WGS84, because the query asks for outSR=4326) so an
adapter can treat coordinates like any other column.

Usage: extract.py <blob> <FORMAT> <out.json> '<limits json>'
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

VERSION = "tables-v8"


def _features_to_rows(features: list[dict], props_key: str, limits: dict) -> list[list]:
    keys: list[str] = []
    seen = set()
    for f in features:
        for k in (f.get(props_key) or {}):
            if k not in seen:
                seen.add(k)
                keys.append(k)
    header = keys + ["_lon", "_lat"]
    rows = [header]
    for f in features:
        if len(rows) > limits["max_rows"]:
            raise ValueError("Row limit exceeded")
        p = f.get(props_key) or {}
        lon = lat = None
        g = f.get("geometry") or {}
        if "x" in g and "y" in g:                       # ArcGIS point
            lon, lat = g.get("x"), g.get("y")
        elif g.get("type") == "Point" and g.get("coordinates"):
            lon, lat = g["coordinates"][:2]
        rows.append([p.get(k) for k in keys] + [lon, lat])
    return rows


class _Tables(HTMLParser):
    """Every <table> in a fragment, as rows of cell text. Nested tables are
    read as their own tables; a cell's text is its text, whitespace folded."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.stack: list[list[list[str]]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.stack.append([])
        elif tag == "tr" and self.stack:
            self.row = []
            self.stack[-1].append(self.row)
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr":
            self.row = None
        elif tag == "table" and self.stack:
            t = self.stack.pop()
            if t:
                self.tables.append(t)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _resplit(page, table) -> list[list[str]] | None:
    """A ruled table whose header row is split into columns but whose data
    rows are each drawn as one cell across the whole table (Newham's
    register: ten ruled header cells, then each licence one wide box, so the
    extractor read the licence as one cell). The header's cells are where
    the columns are: each word in a data row goes to the column its centre
    sits under, in reading order. Only when every data row is one cell
    spanning most of the table; any other table is read as drawn."""
    rows = table.rows
    if len(rows) < 2:
        return None
    head = rows[0].cells
    if sum(1 for c in head if c) < 3:
        return None
    width = table.bbox[2] - table.bbox[0]
    for r in rows[1:]:
        cells = [c for c in r.cells if c]
        if len(cells) != 1 or (cells[0][2] - cells[0][0]) < 0.8 * width:
            return None
    words = page.extract_words()
    names = table.extract()[0]
    out = [[" ".join(str(n).split()) if n else "" for n in names]]
    for r in rows[1:]:
        top, bottom = r.bbox[1], r.bbox[3]
        cols: list[list[dict]] = [[] for _ in head]
        for w in words:
            if not top <= (w["top"] + w["bottom"]) / 2 <= bottom:
                continue
            cx = (w["x0"] + w["x1"]) / 2
            for i, c in enumerate(head):
                if c and c[0] <= cx < c[2]:
                    cols[i].append(w)
                    break
        out.append([" ".join(w["text"] for w in sorted(ws, key=lambda w: (round(w["top"] / 3), w["x0"]))) for ws in cols])
    return out


def extract(path: Path, fmt: str, limits: dict) -> list[dict]:
    tables: list[dict] = []
    total = 0

    def add(rows, **where):
        nonlocal total
        total += len(rows)
        if total > limits["max_rows"]:
            raise ValueError("Row limit exceeded")
        tables.append(dict(**where, rows=rows))

    data = path.read_bytes()
    if fmt == "CSV":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            # cp1252 leaves five bytes undefined (0x81, 0x8d, 0x8f, 0x90,
            # 0x9d); a council's export can carry them. Latin-1 maps every
            # byte, so nothing is lost but the odd accented character.
            try:
                text = data.decode("cp1252")
            except UnicodeDecodeError:
                text = data.decode("latin-1")
        head = text.lstrip()[:200].lower()
        # A file that is nothing but an HTML table, served under a CSV name:
        # Epsom and Ewell's map server applies an XSL called "atcsv" and
        # returns <table><tr><th>... Read as CSV it was one column of tags.
        # Only a document that *starts* with a table is read this way; a
        # whole web page is still refused, since its tables are its layout.
        if head.startswith("<table"):
            parser = _Tables()
            parser.feed(text)
            parser.close()
            found = [t for t in parser.tables if len(t) > 1 and max(map(len, t)) >= 2]
            if not found:
                raise ValueError("HTML fragment with no table of data")
            for i, t in enumerate(found, start=1):
                add(t, table=i, source_markup="html table")
            return tables
        if head.startswith(("<!doctype", "<html")):
            raise ValueError("HTML response, not CSV")
        # The sniffer is trusted for the delimiter only. Its guesses at
        # quoting (doublequote off, for one) broke every brownfield register
        # whose addresses carry commas inside quotes — Hinckley, Rotherham,
        # Cheltenham: fields split and every later column shifted. Excel
        # quoting is what the files use.
        try:
            delimiter = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","

        class _Dialect(csv.excel):
            pass
        _Dialect.delimiter = delimiter
        rows = []
        for row in csv.reader(io.StringIO(text), _Dialect):
            if len(rows) >= limits["max_rows"]:
                raise ValueError("Row limit exceeded")
            rows.append(row)
        if not rows or max(map(len, rows)) < 2:
            raise ValueError("No tabular CSV content")
        add(rows, table=1)
    elif fmt == "ESRI":
        doc = json.loads(data)
        if doc.get("error"):
            raise ValueError("ArcGIS error: " + str(doc["error"])[:200])
        feats = doc.get("features")
        if not isinstance(feats, list):
            raise ValueError("No features in ArcGIS response")
        add(_features_to_rows(feats, "attributes", limits), table=1,
            exceeded=bool(doc.get("exceededTransferLimit")))
    elif fmt == "GEOJSON":
        doc = json.loads(data)
        feats = doc.get("features")
        if not isinstance(feats, list):
            raise ValueError("Not a GeoJSON FeatureCollection")
        add(_features_to_rows(feats, "properties", limits), table=1)
    elif fmt == "JSON":
        doc = json.loads(data)
        if isinstance(doc, dict) and doc.get("error"):
            raise ValueError("API returned an error")
        if isinstance(doc, dict) and isinstance(doc.get("features"), list):
            key = "attributes" if doc["features"] and "attributes" in doc["features"][0] else "properties"
            add(_features_to_rows(doc["features"], key, limits), table=1)
        elif isinstance(doc, list) and doc and isinstance(doc[0], dict):
            keys = list(dict.fromkeys(k for r in doc for k in r))
            add([keys] + [[r.get(k) for k in keys] for r in doc], table=1)
        else:
            raise ValueError("JSON is not a list of records or a feature collection")
    elif fmt == "XLSX":
        import openpyxl
        with zipfile.ZipFile(path) as archive:
            if sum(z.file_size for z in archive.infolist()) > 100_000_000:
                raise ValueError("Expanded XLSX exceeds 100 MB")
        with path.open("rb") as handle:
            book = openpyxl.load_workbook(handle, read_only=True, data_only=True)
            for sheet in book:
                # A sheet's stated width is where formatting ends, not data:
                # Ashfield's HMO register says 16,384 columns and fills 11.
                # The limit is on columns that hold something, read up to a
                # cap; trailing empty cells go and rows are padded back to
                # the table's real width.
                cap = min(sheet.max_column or 200, 200)
                # A cell holding only spaces is empty (Buckinghamshire's rows
                # run to 700 of them), and blank rows after the last record
                # are formatting (Surrey Heath's, Tamworth's): they count
                # towards neither the width nor the row limit. A blank row
                # between records is kept, so a header's row number holds.
                rows, width, blanks = [], 0, 0
                for row in sheet.iter_rows(values_only=True, max_col=cap):
                    vals = list(row)
                    while vals and (vals[-1] is None or (isinstance(vals[-1], str) and not vals[-1].strip())):
                        vals.pop()
                    if not vals:
                        blanks += 1
                        if blanks > 5000:
                            break
                        continue
                    if len(rows) + blanks + total >= limits["max_rows"]:
                        raise ValueError("Row limit exceeded")
                    width = max(width, len(vals))
                    if width > 100:
                        break
                    rows.extend([[] for _ in range(blanks)])
                    blanks = 0
                    rows.append([("" if v is None else v) for v in vals])
                if width > 100:
                    continue                      # not a table of records; see XLS below
                rows = [r + [""] * (width - len(r)) for r in rows]
                if rows and width:
                    add(rows, sheet=sheet.title)
            book.close()
    elif fmt == "XLS":
        # Old-format Excel, still what several councils upload. xlrd 2 reads
        # only .xls; dates arrive as serial numbers and are turned into ISO
        # dates here, so a mapping sees the same thing an XLSX would give.
        import xlrd
        try:
            book = xlrd.open_workbook(file_contents=data, on_demand=True)
        except xlrd.XLRDError as err:
            # Excel's own write protection (Derby's register): the workbook
            # is "encrypted" with the built-in password Excel opens it with,
            # asking nobody. A workbook with a password of its own stays shut.
            if "encrypted" not in str(err).lower():
                raise
            import msoffcrypto
            locked = msoffcrypto.OfficeFile(io.BytesIO(data))
            locked.load_key(password="VelvetSweatshop")
            out = io.BytesIO()
            try:
                locked.decrypt(out)
            except Exception:  # noqa: BLE001
                raise ValueError("Workbook is encrypted with a password of its own") from None
            book = xlrd.open_workbook(file_contents=out.getvalue(), on_demand=True)
        for sheet in book.sheets():
            # As for XLSX: the stated width is formatting (Spelthorne's says
            # 256); the limit is on columns that hold something.
            real = 0
            for i in range(min(sheet.nrows, 5000)):
                vals = sheet.row_values(i, 0, min(sheet.ncols, 200))
                while vals and str(vals[-1]).strip() == "":
                    vals.pop()
                real = max(real, len(vals))
            if real > 100:
                # A sheet this wide is not a table of records (Spelthorne's
                # renewals sheet runs to column 200); the workbook's other
                # sheets are still read, and only a workbook of nothing else fails.
                continue
            rows = []
            for i in range(sheet.nrows):
                if len(rows) + total >= limits["max_rows"]:
                    raise ValueError("Row limit exceeded")
                out_row = []
                for cell in sheet.row(i)[:real]:
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            out_row.append(xlrd.xldate_as_datetime(cell.value, book.datemode).date().isoformat())
                        except (ValueError, OverflowError):
                            out_row.append(cell.value)
                    elif cell.ctype == xlrd.XL_CELL_EMPTY:
                        out_row.append("")
                    else:
                        out_row.append(cell.value)
                rows.append(out_row)
            if rows:
                add(rows, sheet=sheet.name)
        if not tables:
            raise ValueError("Column limit exceeded on every sheet")
    elif fmt == "PDF":
        import pdfplumber
        if data[:5] != b"%PDF-":
            raise ValueError("Not a PDF")
        with pdfplumber.open(path) as pdf:
            if len(pdf.pages) > limits["max_pages"]:
                raise ValueError("Page limit exceeded")
            for pno, page in enumerate(pdf.pages, 1):
                for tno, table in enumerate(page.find_tables(), 1):
                    split = _resplit(page, table)
                    if split:
                        add(split, page=pno, table=tno, bbox=list(table.bbox), strategy="header columns")
                    else:
                        add(table.extract(), page=pno, table=tno, bbox=list(table.bbox))
            # A register laid out as a table without ruled lines (most council
            # PDFs made from a spreadsheet's print view): the columns are read
            # from the text's own alignment instead, page by page, and marked
            # as such so a reviewer knows the columns were inferred.
            # A register whose header alone is ruled (Tonbridge and Malling,
            # Tameside): its tables carry a header and no rows, and the rows
            # are read by alignment like an unruled register's.
            def _records(t):
                return sum(1 for r in t["rows"] if sum(1 for v in r if v not in (None, "") and str(v).strip()) >= 2)
            if tables and all(_records(t) <= 1 for t in tables):
                tables.clear()
            if not tables:
                for pno, page in enumerate(pdf.pages, 1):
                    t = page.extract_table({"vertical_strategy": "text", "horizontal_strategy": "text"})
                    if t and len(t) > 1 and max(map(len, t)) >= 2:
                        add([[("" if v is None else v) for v in r] for r in t], page=pno, table=1, strategy="text")
        if not tables:
            raise ValueError("No table in the PDF, ruled or by alignment; layout adapter required")
    elif fmt == "HTML":
        # A register published as a table on a web page (Norwich, Rochford,
        # Castle Point): every table on the page with two columns and three
        # rows or more; a page's layout tables rarely have both.
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252", "replace")
        parser = _Tables()
        parser.feed(text)
        parser.close()
        found = [t for t in parser.tables if len(t) >= 3 and max(map(len, t)) >= 2]
        if not found:
            raise ValueError("No table of data on the page")
        for i, t in enumerate(found, start=1):
            add(t, table=i, source_markup="html page")
    elif fmt == "ODS":
        import pandas as pd
        for name, frame in pd.read_excel(path, engine="odf", sheet_name=None, header=None, dtype=str).items():
            rows = [["" if (v is None or (isinstance(v, float) and v != v)) else str(v) for v in r] for r in frame.itertuples(index=False)]
            if len(rows) + total > limits["max_rows"]:
                raise ValueError("Row limit exceeded")
            if rows:
                add(rows, sheet=str(name))
    elif fmt == "DOCX":
        import docx
        doc = docx.Document(str(path))
        for i, t in enumerate(doc.tables, start=1):
            rows = [[" ".join(c.text.split()) for c in r.cells] for r in t.rows]
            if len(rows) > 1:
                add(rows, table=i)
        if not tables:
            raise ValueError("No table in the document")
    elif fmt == "ZIP":
        # A register shipped inside a ZIP (Powys): the one spreadsheet, CSV or
        # PDF in it is read as itself. More than one, and it is a bundle, not
        # a register, so the adapter must say which.
        import tempfile
        with zipfile.ZipFile(path) as archive:
            if sum(z.file_size for z in archive.infolist()) > 100_000_000:
                raise ValueError("Expanded ZIP exceeds 100 MB")
            kinds = {".xlsx": "XLSX", ".xls": "XLS", ".csv": "CSV", ".pdf": "PDF", ".ods": "ODS", ".docx": "DOCX"}
            inner = [z for z in archive.infolist() if not z.is_dir() and Path(z.filename).suffix.lower() in kinds]
            if len(inner) != 1:
                raise ValueError(f"ZIP holds {len(inner)} readable files, not one")
            with tempfile.TemporaryDirectory() as tmp:
                member = Path(tmp) / Path(inner[0].filename).name
                member.write_bytes(archive.read(inner[0]))
                for t in extract(member, kinds[member.suffix.lower()], limits):
                    add(t.pop("rows"), **t, zip_member=inner[0].filename)
    else:
        raise ValueError(f"Unsupported format {fmt}")
    return tables


def main() -> int:
    blob, fmt, out, limits = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
    tables = extract(Path(blob), fmt, limits)
    payload = json.dumps({"version": VERSION, "format": fmt, "tables": tables},
                         ensure_ascii=False, default=str)
    if len(payload) > limits["max_output_bytes"]:
        raise ValueError("Extraction output exceeds byte limit")
    Path(out).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - the parent reads stderr
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
