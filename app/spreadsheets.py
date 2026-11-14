"""CSV and Excel downloads.

Text that starts with = + - @ is prefixed with an apostrophe so that Excel does
not run it as a formula (CSV/formula injection).
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal

from flask import Response
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

MONEY = "money"
PERCENT = "percent"
DATE = "date"
NUMBER_FORMATS = {MONEY: '"$"#,##0.00', PERCENT: "0.##%", DATE: "mm/dd/yyyy"}


def safe_text(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%m/%d/%Y")
    if isinstance(value, Decimal):
        return format(value, "f")
    return safe_text(value)


def _download(data: bytes, filename: str, mimetype: str) -> Response:
    return Response(
        data,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


def csv_response(filename: str, header: list[str], rows) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_value(v) for v in row])
    # UTF-8 with BOM so Excel opens accented names correctly.
    return _download(("﻿" + buf.getvalue()).encode("utf-8"), filename, "text/csv")


def xlsx_response(filename: str, sheets: list[dict]) -> Response:
    """sheets: [{"title", "header", "rows", "formats": {col_index: MONEY|PERCENT|DATE}, "total_row": bool}]"""
    wb = Workbook()
    wb.remove(wb.active)

    for sheet in sheets:
        ws = wb.create_sheet(title=sheet["title"][:31])
        header = sheet["header"]
        formats = sheet.get("formats", {})
        ws.append(header)
        for cell in ws[1]:
            cell.font = Font(bold=True)

        widths = [len(str(h)) for h in header]
        for row in sheet["rows"]:
            values = []
            for v in row:
                if isinstance(v, Decimal):
                    v = float(v)
                values.append(safe_text(v))
            ws.append(values)
            for i, v in enumerate(values):
                if v is not None:
                    widths[i] = max(widths[i], min(len(str(v)), 60))

        for col_idx, fmt in formats.items():
            letter = get_column_letter(col_idx + 1)
            for cell in ws[letter][1:]:
                cell.number_format = NUMBER_FORMATS[fmt]

        if sheet.get("total_row") and ws.max_row > 1:
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)

        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 9), 62)
        ws.freeze_panes = "A2"
        if ws.max_row > 1:
            last = ws.max_row - 1 if sheet.get("total_row") else ws.max_row
            ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{last}"

    buf = io.BytesIO()
    wb.save(buf)
    return _download(
        buf.getvalue(), filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
