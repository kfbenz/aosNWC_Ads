# Copyright 2026 Archdiocese of Seattle
# Author: Kevin F Benz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Mailing labels as PDF on Avery 5160 / 8160 sheets (30 per letter page, 1" x 2-5/8").

Print at "Actual size" (100%), not "Fit to page", or the labels will drift.
"""
from __future__ import annotations

import io

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


AVERY_5160 = {
    "cols": 3,
    "rows": 10,
    "label_w": 2.625 * inch,
    "label_h": 1.0 * inch,
    "left": 0.1875 * inch,
    "top": 0.5 * inch,
    "h_pitch": 2.75 * inch,  # label width + 0.125" gutter
    "v_pitch": 1.0 * inch,
}
PER_SHEET = AVERY_5160["cols"] * AVERY_5160["rows"]

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_SIZE = 9
LEADING = 10.5
PADDING_X = 0.15 * inch
MAX_LINES = 5


def account_label_lines(account, include_contact: bool = False) -> list[str]:
    """Advertiser, [Contact], Address, Address 2, City, ST Zip; blank lines dropped."""
    city_line = (account.city or "").strip()
    state_zip = " ".join(p for p in ((account.state_code or "").strip(), (account.postal_code or "").strip()) if p)
    if city_line and state_zip:
        city_line = f"{city_line}, {state_zip}"
    else:
        city_line = city_line or state_zip

    lines = [account.advertiser]
    if include_contact:
        lines.append(account.contact_name)
    lines += [account.address1, account.address2, city_line]
    return [line.strip() for line in lines if line and line.strip()][:MAX_LINES]


def _fit(text: str, font: str, max_width: float) -> str:
    if stringWidth(text, font, FONT_SIZE) <= max_width:
        return text
    while text and stringWidth(text + "...", font, FONT_SIZE) > max_width:
        text = text[:-1]
    return text.rstrip() + "..."


def build_labels_pdf(labels: list[list[str]], start_position: int = 1, title: str = "Mailing labels") -> bytes:
    """labels: one list of text lines per label. start_position 1-30 skips used labels on the first sheet."""
    spec = AVERY_5160
    _, page_h = letter
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    pdf.setTitle(title)

    max_width = spec["label_w"] - 2 * PADDING_X
    slot = max(1, min(start_position, PER_SHEET)) - 1

    for lines in labels:
        if slot == PER_SHEET:
            pdf.showPage()
            slot = 0
        row, col = divmod(slot, spec["cols"])
        x = spec["left"] + col * spec["h_pitch"] + PADDING_X
        label_top = page_h - spec["top"] - row * spec["v_pitch"]

        block_h = len(lines) * LEADING
        y = label_top - (spec["label_h"] - block_h) / 2 - FONT_SIZE
        for i, text in enumerate(lines):
            font = FONT_BOLD if i == 0 else FONT
            pdf.setFont(font, FONT_SIZE)
            pdf.drawString(x, y, _fit(text, font, max_width))
            y -= LEADING
        slot += 1

    pdf.save()
    return buf.getvalue()
