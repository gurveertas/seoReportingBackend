import io
import math
from html import escape
from pathlib import Path
from typing import Any

import reportlab
from app.reports.pagespeed import pagespeed_section

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


_NAVY = colors.HexColor("#102A43")
_TEAL = colors.HexColor("#0F766E")
_BLUE = colors.HexColor("#3563A9")
_GREEN = colors.HexColor("#16835D")
_RED = colors.HexColor("#B54745")
_MUTED = colors.HexColor("#526477")
_GRID = colors.HexColor("#D7E1E9")
_PALE = colors.HexColor("#F3F7FA")
_CARD = colors.white
_BANNER_SUBTITLE = colors.HexColor("#D7E4EC")
_GOLD = colors.HexColor("#D9AA4B")
_FONT = "SEOReportVera"
_FONT_BOLD = "SEOReportVera-Bold"
_FONT_ITALIC = "SEOReportVera-Italic"
_FONT_BOLD_ITALIC = "SEOReportVera-BoldItalic"
_FRAME_PADDING = 12  # ReportLab's default frame has 6 pt of padding on each side.
_GUTTER = 8
_TABLE_COLUMN_LABELS = {
    "date": "Date",
    "query": "Query",
    "page": "Landing page",
    "clicks": "Clicks",
    "impressions": "Impressions",
    "ctr_percent": "CTR (%)",
    "position": "Avg. position",
    "totalUsers": "Users",
    "sessions": "Sessions",
    "screenPageViews": "Page views",
}


def _register_fonts() -> None:
    font_directory = Path(reportlab.__file__).parent / "fonts"
    font_files = {
        _FONT: "Vera.ttf",
        _FONT_BOLD: "VeraBd.ttf",
        _FONT_ITALIC: "VeraIt.ttf",
        _FONT_BOLD_ITALIC: "VeraBI.ttf",
    }
    registered_fonts = set(pdfmetrics.getRegisteredFontNames())
    for font_name, filename in font_files.items():
        if font_name not in registered_fonts:
            pdfmetrics.registerFont(
                TTFont(font_name, str(font_directory / filename))
            )
    pdfmetrics.registerFontFamily(
        _FONT,
        normal=_FONT,
        bold=_FONT_BOLD,
        italic=_FONT_ITALIC,
        boldItalic=_FONT_BOLD_ITALIC,
    )


def _safe_text(value: Any) -> str:
    return str(value).encode("latin-1", "replace").decode("latin-1")


def _format_number(value: Any) -> str:
    if value is None:
        return "No data"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return _safe_text(value)


def _kpi_change_text(kpi: dict[str, Any]) -> str:
    change = kpi.get("change")
    unit = kpi.get("change_unit")
    trend = kpi.get("trend")
    if change is None or trend == "unavailable":
        return "Comparison unavailable"
    if unit == "positions":
        if trend == "steady":
            return "No change in position"
        wording = "better" if trend == "up" else "worse"
        return f"{abs(change):.2f} positions {wording}"
    if unit == "percentage_points":
        return f"{change:+.2f} percentage points"
    return f"{change:+.2f}% vs previous period"


class _LineChart(Flowable):
    def __init__(
        self,
        title: str,
        labels: list[str],
        values: list[Any],
        color: colors.Color,
        height: float = 120,
    ):
        super().__init__()
        self.title = title
        self.labels = labels
        self.values = values
        self.color = color
        self.height = height

    def wrap(self, available_width, available_height):
        self.width = available_width
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setFillColor(_CARD)
        canvas.setStrokeColor(_GRID)
        canvas.roundRect(0, 0, self.width, self.height, 6, stroke=1, fill=1)
        canvas.setStrokeColor(_GRID)
        canvas.setFillColor(_NAVY)
        canvas.setFont(_FONT_BOLD, 8.5)
        canvas.drawString(12, self.height - 17, _safe_text(self.title)[:52])

        plot_left = 40
        plot_right = self.width - 20
        plot_bottom = 26
        plot_top = self.height - 29
        plot_width = plot_right - plot_left
        plot_height = plot_top - plot_bottom
        numeric_values = [
            float(value)
            for value in self.values
            if isinstance(value, (int, float)) and math.isfinite(value)
        ]

        if not numeric_values or not self.labels:
            canvas.setFillColor(_MUTED)
            canvas.setFont(_FONT, 8)
            canvas.drawString(plot_left, self.height / 2, "No daily data available")
            canvas.restoreState()
            return

        step = max(1, max(numeric_values) * 1.1 / 4)
        magnitude = 10 ** math.floor(math.log10(step))
        tick_size = math.ceil(step / magnitude) * magnitude
        maximum = tick_size * 4

        for tick in range(5):
            ratio = tick / 4
            y = plot_bottom + plot_height * ratio
            canvas.setStrokeColor(_GRID)
            canvas.line(plot_left, y, plot_right, y)
            canvas.setFillColor(_MUTED)
            canvas.setFont(_FONT, 6)
            canvas.drawRightString(
                plot_left - 4,
                y - 2,
                f"{tick * tick_size:,}",
            )

        canvas.setStrokeColor(self.color)
        canvas.setFillColor(self.color)
        canvas.setLineWidth(1.8)
        points = []
        denominator = max(len(self.values) - 1, 1)
        for index, value in enumerate(self.values):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                points.append(None)
                continue
            x = plot_left + plot_width * index / denominator
            y = plot_bottom + plot_height * max(float(value), 0) / maximum
            points.append((x, y))

        previous_point = None
        for point in points:
            if point is None:
                previous_point = None
                continue
            if previous_point:
                canvas.line(
                    previous_point[0],
                    previous_point[1],
                    point[0],
                    point[1],
                )
            canvas.circle(point[0], point[1], 2.2, stroke=0, fill=1)
            previous_point = point

        label_count = min(len(self.labels), 6, max(2, int(plot_width / 35)))
        label_indices = (
            round(index * (len(self.labels) - 1) / max(label_count - 1, 1))
            for index in range(label_count)
        )
        canvas.setFillColor(_MUTED)
        canvas.setFont(_FONT, 6)
        for index in label_indices:
            x = plot_left + plot_width * index / denominator
            label_text = _safe_text(self.labels[index])
            if len(label_text) == 10 and label_text[4] == "-" and label_text[7] == "-":
                label_text = label_text[-5:]
            canvas.drawCentredString(x, 11, label_text)

        canvas.restoreState()


class _PlanPill(Paragraph):
    def draw(self):
        width = max(self.getActualLineWidths0(), default=0) + 16
        self.canv.saveState()
        self.canv.setFillColor(colors.HexColor("#DBF2EF"))
        self.canv.setStrokeColor(_TEAL)
        self.canv.setLineWidth(0.9)
        self.canv.roundRect(0, -3, min(self.width, width), self.height + 6, 9, stroke=1, fill=1)
        self.canv.restoreState()
        super().draw()


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_safe_text(value if value is not None else "")), style)


def _make_kpi_card(kpi: dict[str, Any], styles, hide_comparison: bool) -> list[Paragraph]:
    trend = kpi.get("trend")
    change_color = _GREEN if trend == "up" else _RED if trend == "down" else _MUTED
    card_accent = _BLUE if str(kpi.get("key", "")).startswith("ga4_") else _TEAL
    change_style = ParagraphStyle(
        "AnalyticsKpiChangeValue",
        parent=styles["kpi_change"],
        textColor=change_color,
    )
    label_style = ParagraphStyle(
        "AnalyticsKpiSource", parent=styles["kpi_label"], textColor=card_accent
    )
    value = _format_number(kpi.get("value"))
    if kpi.get("key") == "gsc_ctr" and kpi.get("value") is not None:
        value += "%"
    paragraphs = [
        _paragraph(kpi.get("label", ""), label_style),
        _paragraph(value, styles["kpi_value"]),
    ]
    if not hide_comparison:
        paragraphs.append(_paragraph(_kpi_change_text(kpi), change_style))
    return paragraphs


def _panel_row(
    panels: list[Flowable] | list[list[Paragraph]],
    width: float,
    *,
    metric_cards: bool = False,
) -> Table:
    panel_width = (width - _GUTTER * (len(panels) - 1)) / len(panels)
    cells = []
    widths = []
    for panel in panels:
        if cells:
            cells.append("")
            widths.append(_GUTTER)
        cells.append(panel)
        widths.append(panel_width)

    padding = 7 if metric_cards else 0
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
    ]
    if metric_cards:
        for index in range(0, len(cells), 2):
            cell = (index, 0)
            commands.extend([
                ("BACKGROUND", cell, cell, _PALE),
                ("BOX", cell, cell, 0.6, _GRID),
            ])
    return Table(
        [cells], colWidths=widths, hAlign="LEFT", spaceAfter=_GUTTER,
        style=TableStyle(commands),
    )


def _data_table(
    title: str,
    data: dict[str, Any],
    styles,
    available_width: float,
    limit: int | None = None,
    *,
    integration_metrics: bool = True,
) -> Table | None:
    columns = data.get("columns", [])
    rows = data.get("rows", [])
    if limit is not None:
        rows = rows[:limit]
    if not columns or not rows:
        return None

    cell_style = styles["table_cell"]
    header_style = styles["table_header"]
    labels = _TABLE_COLUMN_LABELS if integration_metrics else {}
    table_data = [
        [_paragraph(title, styles["section_heading"])] + [""] * (len(columns) - 1),
        [
            _paragraph(labels.get(column, column), header_style)
            for column in columns
        ],
    ] + [
        [_paragraph(row.get(column, ""), cell_style) for column in columns]
        for row in rows
    ]
    column_widths = [available_width / len(columns)] * len(columns)
    if integration_metrics and len(columns) > 1 and columns[0] in ("query", "page"):
        column_widths[0] = available_width * 0.46
        remaining_width = available_width - column_widths[0]
        column_widths[1:] = [
            remaining_width / (len(columns) - 1)
        ] * (len(columns) - 1)

    return Table(
        table_data,
        colWidths=column_widths,
        repeatRows=2,
        splitInRow=1,
        hAlign="LEFT",
        style=TableStyle(
            [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 1), (-1, 1), _NAVY),
                ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, _PALE]),
                ("BOX", (0, 1), (-1, -1), 0.5, _GRID),
                ("INNERGRID", (0, 1), (-1, -1), 0.25, _GRID),
                ("LINEBELOW", (0, 1), (-1, 1), 1.2, _TEAL),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ]
        ),
    )


def generate_analytics_pdf(
    dashboard: dict[str, Any],
    period: str,
    client_name: str,
    *,
    comparison: bool = False,
    next_plans: list[str] | None = None,
) -> bytes:
    _register_fonts()
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=16 * mm,
        bottomMargin=15 * mm,
        # Spec: Title only. No provider name in Author/Creator/Producer.
        title=f"{_safe_text(client_name)} {period.title()} SEO Report",
        author="",
        creator="",
        producer="",
        subject="",
    )
    content_width = document.width - _FRAME_PADDING
    base_styles = getSampleStyleSheet()
    styles = {
        "banner_eyebrow": ParagraphStyle(
            "AnalyticsBannerEyebrow",
            parent=base_styles["Normal"],
            fontName=_FONT_BOLD,
            fontSize=7.5,
            leading=10,
            textColor=_GOLD,
            spaceAfter=2,
        ),
        "banner_title": ParagraphStyle(
            "AnalyticsBannerTitle",
            parent=base_styles["Title"],
            fontName=_FONT_BOLD,
            fontSize=22,
            leading=27,
            alignment=TA_LEFT,
            textColor=colors.white,
            spaceAfter=3,
        ),
        "banner_subtitle": ParagraphStyle(
            "AnalyticsBannerSubtitle",
            parent=base_styles["Normal"],
            fontName=_FONT,
            fontSize=8,
            leading=12,
            textColor=_BANNER_SUBTITLE,
        ),
        "section_heading": ParagraphStyle(
            "AnalyticsSection",
            parent=base_styles["Heading2"],
            fontName=_FONT_BOLD,
            fontSize=11,
            leading=14,
            textColor=_NAVY,
            spaceBefore=11,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "AnalyticsBody",
            parent=base_styles["BodyText"],
            fontName=_FONT,
            fontSize=8.5,
            leading=12,
            textColor=_NAVY,
        ),
        "kpi_label": ParagraphStyle(
            "AnalyticsKpiLabel",
            parent=base_styles["Normal"],
            fontName=_FONT_BOLD,
            fontSize=7,
            leading=10,
            textColor=_MUTED,
            alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "AnalyticsKpiValue",
            parent=base_styles["Normal"],
            fontName=_FONT_BOLD,
            fontSize=16,
            leading=20,
            textColor=_NAVY,
            alignment=TA_CENTER,
        ),
        "kpi_change": ParagraphStyle(
            "AnalyticsKpiChange",
            parent=base_styles["Normal"],
            fontName=_FONT,
            fontSize=7,
            leading=10,
            textColor=_MUTED,
            alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "AnalyticsTableHeader",
            parent=base_styles["Normal"],
            fontName=_FONT_BOLD,
            fontSize=7.5,
            leading=10,
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "AnalyticsTableCell",
            parent=base_styles["Normal"],
            fontName=_FONT,
            fontSize=7.5,
            leading=10,
            textColor=_NAVY,
        ),
    }

    period_data = dashboard.get("period", {})
    gsc_source = dashboard.get("sources", {}).get("gsc", {})
    site_url = gsc_source.get("site_url")
    subtitle_parts = [f"Prepared for {_safe_text(client_name)}"]
    for label, start_key, end_key in (
        ("Reporting period", "start_date", "end_date"),
        ("Compared with", "comparison_start_date", "comparison_end_date"),
    ):
        start, end = period_data.get(start_key), period_data.get(end_key)
        if start and end and not (comparison and start_key == "comparison_start_date"):
            subtitle_parts.append(f"{label}: {start} to {end}")
    if site_url:
        subtitle_parts.append(f"Search Console property: {_safe_text(site_url)}")

    banner = Table(
        [
            [_paragraph("SEO PERFORMANCE REPORT", styles["banner_eyebrow"])],
            [
                _paragraph(
                    f"{period.title()} Search & Traffic Overview",
                    styles["banner_title"],
                )
            ],
            [
                _paragraph(
                    "  |  ".join(subtitle_parts),
                    styles["banner_subtitle"],
                )
            ],
        ],
        colWidths=[content_width],
        hAlign="LEFT",
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                ("LINEABOVE", (0, 0), (-1, 0), 3, _TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 15),
                ("RIGHTPADDING", (0, 0), (-1, -1), 15),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
                ("TOPPADDING", (0, 2), (-1, 2), 0),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 13),
            ]
        )
    )
    story: list[Flowable] = [
        banner,
        Paragraph("Performance indicators", styles["section_heading"]),
    ]

    kpis = dashboard.get("kpis", [])
    if any(kpi.get("value") is not None for kpi in kpis):
        for index in range(0, len(kpis), 4):
            cards = [_make_kpi_card(kpi, styles, comparison) for kpi in kpis[index : index + 4]]
            story.append(
                _panel_row(cards, content_width, metric_cards=True)
            )
    else:
        story.append(Paragraph("No KPI data is stored for this period.", styles["body"]))

    chart_flowables = []
    palette = [
        _TEAL,
        _BLUE,
        _GOLD,
        colors.HexColor("#78649A"),
        _GREEN,
    ]
    source_labels = {"gsc_daily": "Search Console", "ga4_daily": "Analytics"}
    metric_labels = {"totalUsers": "Users", "screenPageViews": "Page views"}
    for chart_key, chart in dashboard.get("charts", {}).items():
        source = source_labels.get(chart_key, chart_key.replace("_", " ").title())
        labels = chart.get("labels", [])
        for dataset_index, dataset in enumerate(chart.get("datasets", [])):
            values = dataset.get("data", [])
            if not labels or not any(
                isinstance(value, (int, float)) and math.isfinite(value)
                for value in values
            ):
                continue
            label = dataset.get("label", "Metric")
            metric = metric_labels.get(label, label.capitalize())
            chart_flowables.append(
                _LineChart(
                    f"{source} | {metric}",
                    labels,
                    values,
                    palette[dataset_index % len(palette)],
                )
            )

    if chart_flowables:
        story.append(Paragraph("Daily trends", styles["section_heading"]))
        for index in range(0, len(chart_flowables), 2):
            story.append(
                _panel_row(chart_flowables[index : index + 2], content_width)
            )
    else:
        story.append(Paragraph("No daily trend data is stored for this period.", styles["body"]))

    tables = dashboard.get("tables", {})
    detail_sections = (
        ("gsc_daily", "Daily Search Console performance", None),
        ("top_queries", "Highest-click search queries", None),
        ("top_pages", "Highest-click landing pages", None),
        ("ga4_daily", "Daily Analytics performance", None),
        ("google_sheets", "Google Sheets data", 20),
    )
    sections_without_data = []
    for key, title, limit in detail_sections:
        table_data = tables.get(key, {})
        table_title = title
        if limit is not None and len(table_data.get("rows", [])) > limit:
            table_title = f"{title} (first {limit} rows)"
        table = _data_table(
            table_title, table_data, styles, content_width, limit,
            integration_metrics=key != "google_sheets",
        )
        if table is not None:
            story.append(table)
        else:
            sections_without_data.append(title)

    if len(sections_without_data) == len(detail_sections):
        story.append(Paragraph("No detailed data is stored for this period.", styles["body"]))
    elif sections_without_data:
        missing = ", ".join(sections_without_data)
        story.extend([
            Spacer(1, 6),
            _paragraph(f"No stored data for {missing}.", styles["body"]),
        ])

    story.extend(pagespeed_section(site_url, styles["section_heading"], styles["body"]))

    plans = [plan.strip() for plan in next_plans or [] if plan.strip()]
    if plans:
        heading = "Next week plan" if period == "weekly" else "Next month plan"
        story.append(Paragraph(heading, styles["section_heading"]))
        pill_style = ParagraphStyle(
            "PlanPill", parent=styles["body"], leftIndent=8, rightIndent=8,
            fontName=_FONT_BOLD, textColor=_NAVY, spaceBefore=8, spaceAfter=15,
        )
        for plan in plans:
            story.append(_PlanPill(escape(plan), pill_style))

    def draw_page(canvas, doc):
        left = doc.leftMargin + _FRAME_PADDING / 2
        right = A4[0] - doc.rightMargin - _FRAME_PADDING / 2
        canvas.saveState()
        canvas.setFillColor(_NAVY)
        canvas.setFont(_FONT_BOLD, 7.5)
        canvas.drawString(
            left,
            A4[1] - 10 * mm,
            "SEO REPORTING",
        )
        canvas.setFillColor(_TEAL)
        canvas.setFont(_FONT_BOLD, 7)
        canvas.drawRightString(
            right,
            A4[1] - 10 * mm,
            f"{period.upper()} REPORT",
        )
        canvas.setStrokeColor(_GRID)
        canvas.line(
            left,
            A4[1] - 13 * mm,
            right,
            A4[1] - 13 * mm,
        )
        canvas.line(left, 11 * mm, right, 11 * mm)
        canvas.setFillColor(_MUTED)
        canvas.setFont(_FONT, 7)
        canvas.drawString(left, 7 * mm, "Generated from stored integration data")
        canvas.drawRightString(right, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output.getvalue()
