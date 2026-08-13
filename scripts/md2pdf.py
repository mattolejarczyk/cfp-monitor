"""Render the Nicolia agenda markdown to a print-ready PDF."""
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (HRFlowable, ListFlowable, ListItem, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

SRC, OUT = sys.argv[1], sys.argv[2]

INK = colors.HexColor("#15181d")
MUTED = colors.HexColor("#5b6472")
ACCENT = colors.HexColor("#1b4d8f")
LINE = colors.HexColor("#d8dde5")
QUOTEBG = colors.HexColor("#f4f6f9")

ss = getSampleStyleSheet()
S = {
    "h1": ParagraphStyle("h1", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=19,
                         leading=23, textColor=INK, alignment=TA_LEFT, spaceAfter=2),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13.5, leading=17,
                         textColor=ACCENT, spaceBefore=15, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=11, leading=14,
                         textColor=INK, spaceBefore=10, spaceAfter=4),
    "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.7, leading=13.6,
                        textColor=INK, spaceAfter=7),
    "quote": ParagraphStyle("quote", fontName="Helvetica-Oblique", fontSize=9.7, leading=13.8,
                            textColor=colors.HexColor("#2c3340"), leftIndent=14, rightIndent=8,
                            spaceBefore=3, spaceAfter=8, borderPadding=(7, 7, 7, 9),
                            backColor=QUOTEBG, borderColor=colors.HexColor("#c9d3e2"),
                            borderWidth=0),
    "li": ParagraphStyle("li", fontName="Helvetica", fontSize=9.7, leading=13.4,
                         textColor=INK, spaceAfter=2.5),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.9, leading=11.6,
                           textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=8.9, leading=11.6,
                            textColor=colors.white),
}


def inline(t):
    """Markdown inline -> reportlab markup. Escape first, then style."""
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8.8">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", t)
    return t


def table(rows):
    head, body = rows[0], rows[1:]
    data = [[Paragraph(inline(c), S["cellh"]) for c in head]]
    data += [[Paragraph(inline(c), S["cell"]) for c in r] for r in body]
    ncol = len(head)
    avail = 6.9 * inch
    widths = [avail * 0.30] + [avail * 0.70 / (ncol - 1)] * (ncol - 1) if ncol > 1 else [avail]
    t = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
    ]))
    return t


story, buf_tbl, buf_li = [], [], []
lines = open(SRC, encoding="utf-8").read().splitlines()


def flush():
    global buf_tbl, buf_li
    if buf_tbl:
        story.append(Spacer(1, 3))
        story.append(table(buf_tbl))
        story.append(Spacer(1, 9))
        buf_tbl = []
    if buf_li:
        story.append(ListFlowable(
            [ListItem(Paragraph(inline(x), S["li"]), leftIndent=13) for x in buf_li],
            bulletType="bullet", bulletFontSize=6, bulletOffsetY=-1.5,
            leftIndent=13, bulletColor=ACCENT))
        story.append(Spacer(1, 6))
        buf_li = []


for raw in lines:
    ln = raw.rstrip()
    if re.match(r"^\|[\s-]*\|", ln.replace(":", "")) and set(ln) <= set("|- :"):
        continue                                            # table separator row
    if ln.startswith("|"):
        buf_tbl.append([c.strip() for c in ln.strip("|").split("|")])
        continue
    flush()
    if not ln.strip():
        continue
    if ln.startswith("### "):
        story.append(Paragraph(inline(ln[4:]), S["h3"]))
    elif ln.startswith("## "):
        story.append(Paragraph(inline(ln[3:]), S["h2"]))
    elif ln.startswith("# "):
        story.append(Paragraph(inline(ln[2:]), S["h1"]))
    elif ln.startswith("---"):
        story.append(Spacer(1, 5))
        story.append(HRFlowable(width="100%", thickness=0.6, color=LINE,
                                spaceBefore=2, spaceAfter=8))
    elif ln.startswith("> "):
        story.append(Paragraph(inline(ln[2:]), S["quote"]))
    elif re.match(r"^[-*] ", ln):
        buf_li.append(ln[2:])
    else:
        story.append(Paragraph(inline(ln), S["p"]))
flush()


def footer(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 7.5)
    canv.setFillColor(MUTED)
    canv.drawString(0.8 * inch, 0.55 * inch, "Nicolia meeting agenda  -  2026-08-12")
    canv.drawRightString(LETTER[0] - 0.8 * inch, 0.55 * inch, f"Page {canv.getPageNumber()}")
    canv.setStrokeColor(LINE)
    canv.setLineWidth(0.4)
    canv.line(0.8 * inch, 0.72 * inch, LETTER[0] - 0.8 * inch, 0.72 * inch)
    canv.restoreState()


SimpleDocTemplate(OUT, pagesize=LETTER,
                  leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                  topMargin=0.7 * inch, bottomMargin=0.85 * inch,
                  title="Nicolia meeting agenda - 2026-08-12",
                  author="PRIME|PR conference monitor").build(story, onFirstPage=footer,
                                                              onLaterPages=footer)
print(f"wrote {OUT}")
