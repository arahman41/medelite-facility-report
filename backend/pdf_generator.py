import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import Flowable


MEDELITE_PURPLE = colors.HexColor("#7B2D8B")
MEDELITE_TEAL   = colors.HexColor("#00A89D")
ROW_ALT         = colors.HexColor("#FAFAFA")
DARK_TEXT       = colors.HexColor("#1A1A1A")
LABEL_BG        = colors.HexColor("#EFEFEF")
ABOVE_GREEN     = colors.HexColor("#2E7D32")
BELOW_RED       = colors.HexColor("#C62828")
TABLE_BORDER    = colors.HexColor("#CCCCCC")


def benchmark_label(facility_val, nat_val, lower_is_better=True):
    """Compare facility value to national average. Lower is better for hospitalization rates."""
    try:
        fv = float(str(facility_val).replace("%", ""))
        nv = float(str(nat_val).replace("%", ""))
        if lower_is_better:
            if fv < nv:
                return ABOVE_GREEN, "Below Nat. Avg."
            elif fv > nv:
                return BELOW_RED, "Above Nat. Avg."
            else:
                return DARK_TEXT, "At Nat. Avg."
        else:
            if fv > nv:
                return ABOVE_GREEN, "Above Nat. Avg."
            elif fv < nv:
                return BELOW_RED, "Below Nat. Avg."
            else:
                return DARK_TEXT, "At Nat. Avg."
    except Exception:
        return DARK_TEXT, ""


def generate_pdf(data: dict, buf):
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.25 * inch,
        bottomMargin=0.3 * inch,
    )

    styles = getSampleStyleSheet()

    brand_title = ParagraphStyle(
        "BrandTitle",
        fontSize=22,
        fontName="Helvetica-Bold",
        textColor=MEDELITE_PURPLE,
        alignment=TA_CENTER,
        leading=28,
        spaceAfter=4,
    )
    brand_sub = ParagraphStyle(
        "BrandSub",
        fontSize=11,
        fontName="Helvetica",
        textColor=MEDELITE_TEAL,
        alignment=TA_CENTER,
        leading=16,
        spaceBefore=2,
        spaceAfter=6,
    )
    section_header = ParagraphStyle(
        "SectionHeader",
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
        spaceAfter=0,
        leading=16,
    )
    state_style = ParagraphStyle(
        "StateStyle",
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=DARK_TEXT,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    label_style = ParagraphStyle(
        "LabelStyle",
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
        leading=11,
    )
    value_style = ParagraphStyle(
        "ValueStyle",
        fontSize=9,
        fontName="Helvetica",
        textColor=DARK_TEXT,
        alignment=TA_LEFT,
        leading=11,
    )
    link_style = ParagraphStyle(
        "LinkStyle",
        fontSize=8,
        fontName="Helvetica",
        textColor=MEDELITE_TEAL,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    footer_style = ParagraphStyle(
        "FooterStyle",
        fontSize=7,
        fontName="Helvetica",
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
    )

    story = []

    # Logo header - falls back to text if logo.png is missing
    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(logo_path):
        logo = RLImage(logo_path, width=2.8 * inch, height=0.89 * inch)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 2))
    else:
        story.append(Paragraph("INFINITE", brand_title))
        story.append(Spacer(1, 4))
        story.append(Paragraph("Managed by MEDELITE", brand_sub))

    story.append(HRFlowable(width="100%", thickness=2, color=MEDELITE_PURPLE, spaceAfter=2))

    title_data = [[Paragraph("FACILITY ASSESSMENT SNAPSHOT", section_header)]]
    title_table = Table(title_data, colWidths=[7.3 * inch])
    title_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), MEDELITE_PURPLE),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(title_table)
    story.append(Spacer(1, 1))

    state = data.get("state", "")
    story.append(Paragraph(state, state_style))
    story.append(Spacer(1, 2))

    ccn = data.get("ccn", "")
    medicare_url = f"https://www.medicare.gov/care-compare/details/nursing-home/{ccn}"
    story.append(Paragraph(
        f'<link href="{medicare_url}" color="{MEDELITE_TEAL.hexval()}">Medicare Care Compare: {medicare_url}</link>',
        link_style
    ))
    story.append(Spacer(1, 2))

    display_name = data.get("name_override") or data.get("name") or ""
    address_full = ", ".join(filter(None, [
        data.get("address", ""),
        data.get("city", ""),
        data.get("state", ""),
        data.get("zip", ""),
    ]))

    def lbl(text):
        return Paragraph(text, label_style)

    def val(text):
        return Paragraph(str(text) if text else "", value_style)

    def star_val(rating):
        if not rating:
            return Paragraph("N/A", value_style)
        try:
            return Paragraph(str(int(rating)), value_style)
        except Exception:
            return Paragraph(str(rating), value_style)

    col_w = [2.6 * inch, 4.7 * inch]

    def make_row(label, value):
        return [lbl(label), value if not isinstance(value, str) else val(value)]

    rows = [
        make_row("Name of Facility", display_name),
        make_row("Location", address_full),
        make_row("EMR", data.get("emr", "")),
        make_row("Census Capacity", str(data.get("certified_beds", ""))),
        make_row("Current Census", str(data.get("current_census", ""))),
        make_row("Type of Patient", data.get("patient_type", "")),
        make_row("Previous Coverage from Medelite", data.get("prev_coverage", "")),
        make_row("Previous Provider Performance from Medelite", data.get("prev_performance", "")),
        make_row("Medical Coverage", data.get("medical_coverage", "")),
    ]

    rows.append([
        Paragraph("STAR RATINGS", ParagraphStyle(
            "SRHeader", fontSize=9, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_CENTER
        )),
        Paragraph("CMS Five-Star Quality Rating System", ParagraphStyle(
            "SRSubHeader", fontSize=9, fontName="Helvetica",
            textColor=colors.white, alignment=TA_LEFT
        ))
    ])

    rows.append(make_row("Overall Star Rating", star_val(data.get("overall_rating"))))
    rows.append(make_row("Health Inspection", star_val(data.get("health_inspection_rating"))))
    rows.append(make_row("Staffing", star_val(data.get("staffing_rating"))))
    rows.append(make_row("Quality of Resident Care", star_val(data.get("qm_rating"))))

    rows.append([
        Paragraph("HOSPITALIZATION & ED METRICS", ParagraphStyle(
            "HospHeader", fontSize=9, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_CENTER
        )),
        Paragraph("Short-Term & Long-Term Performance vs. Benchmarks", ParagraphStyle(
            "HospSubHeader", fontSize=9, fontName="Helvetica",
            textColor=colors.white, alignment=TA_LEFT
        ))
    ])

    # Color map for benchmark badges
    COLOR_HEX = {
        ABOVE_GREEN: "2E7D32",
        BELOW_RED:   "C62828",
        DARK_TEXT:   "1A1A1A",
    }

    def hosp_val_with_badge(facility_v, nat_v):
        if not facility_v:
            return val("")
        col, badge = benchmark_label(facility_v, nat_v, lower_is_better=True)
        hex_str = COLOR_HEX.get(col, "1A1A1A")
        badge_text = f' <font color="#{hex_str}">  [{badge}]</font>' if badge else ""
        return Paragraph(
            f"{facility_v}{badge_text}",
            ParagraphStyle("HospVal", fontSize=9, fontName="Helvetica",
                           textColor=DARK_TEXT, alignment=TA_LEFT)
        )

    rows.append(make_row("Short Term Hospitalization",
                         hosp_val_with_badge(data.get("str_hosp"), data.get("str_hosp_nat"))))
    rows.append(make_row("STR National Avg. for Hospitalization", val(data.get("str_hosp_nat", ""))))
    rows.append(make_row("STR State Avg. for Hospitalization",    val(data.get("str_hosp_state", ""))))
    rows.append(make_row("STR ED Visit",
                         hosp_val_with_badge(data.get("str_ed"), data.get("str_ed_nat"))))
    rows.append(make_row("STR ED Visits National Avg.", val(data.get("str_ed_nat", ""))))
    rows.append(make_row("STR ED Visits State Avg.",    val(data.get("str_ed_state", ""))))
    rows.append(make_row("LT Hospitalization",
                         hosp_val_with_badge(data.get("lt_hosp"), data.get("lt_hosp_nat"))))
    rows.append(make_row("LT National Avg. for Hospitalization", val(data.get("lt_hosp_nat", ""))))
    rows.append(make_row("LT State Avg. for Hospitalization",    val(data.get("lt_hosp_state", ""))))
    rows.append(make_row("ED Visit (LT per 1000)",
                         hosp_val_with_badge(data.get("lt_ed"), data.get("lt_ed_nat"))))
    rows.append(make_row("LT ED Visits National Avg.", val(data.get("lt_ed_nat", ""))))
    rows.append(make_row("LT ED Visits State Avg.",    val(data.get("lt_ed_state", ""))))

    table = Table(rows, colWidths=col_w)
    ts = TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.5, TABLE_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (0, 0), (0, -1),  LABEL_BG),
    ])

    for i in range(len(rows)):
        bg = colors.white if i % 2 == 0 else ROW_ALT
        ts.add("BACKGROUND", (1, i), (1, i), bg)

    # Row 9 = star ratings section header (purple)
    ts.add("BACKGROUND", (0, 9),  (1, 9),  MEDELITE_PURPLE)
    ts.add("SPAN",        (0, 9),  (1, 9))
    # Row 14 = hospitalization section header (teal)
    ts.add("BACKGROUND", (0, 14), (1, 14), MEDELITE_TEAL)
    ts.add("SPAN",        (0, 14), (1, 14))

    table.setStyle(ts)
    story.append(table)
    story.append(Spacer(1, 4))

    story.append(HRFlowable(width="100%", thickness=0.5,
                            color=colors.HexColor("#CCCCCC"), spaceAfter=4))
    story.append(Paragraph(
        f"Data sourced from CMS Provider Data Catalog. "
        f"Report generated by INFINITE, Managed by MEDELITE. CCN: {ccn}",
        footer_style
    ))

    doc.build(story)
