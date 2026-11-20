import io
import math
from html import escape
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


_NAVY = colors.HexColor("#18324B")
_TEAL = colors.HexColor("#087E8B")
_GREEN = colors.HexColor("#238636")
_RED = colors.HexColor("#C0392B")
_MUTED = colors.HexColor("#64748B")
_GRID = colors.HexColor("#DCE4EA")
_PALE = colors.HexColor("#F2F6F8")


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
        width: float,
        height: float = 145,
    ):
        super().__init__()
        self.title = title
        self.labels = labels
        self.values = values
        self.color = color
        self.width = width
        self.height = height

    def wrap(self, available_width, available_height):
        self.width = available_width
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.setStrokeColor(_GRID)
        canvas.setFillColor(_NAVY)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(4, self.height - 13, _safe_text(self.title)[:52])

        plot_left = 34
        plot_right = max(plot_left + 1, self.width - 8)
        plot_bottom = 29
        plot_top = self.height - 25
        plot_width = plot_right - plot_left
        plot_height = plot_top - plot_bottom
        numeric_values = [
            float(value)
            for value in self.values
            if isinstance(value, (int, float)) and math.isfinite(value)
        ]

        if not numeric_values or not self.labels:
            canvas.setFillColor(_MUTED)
            canvas.setFont("Helvetica", 8)
            canvas.drawString(plot_left, self.height / 2, "No daily data available")
            canvas.restoreState()
            return

        maximum = max(numeric_values)
        if maximum <= 0:
            maximum = 1
        maximum *= 1.1

        for tick in range(5):
            ratio = tick / 4
            y = plot_bottom + plot_height * ratio
            canvas.setStrokeColor(_GRID)
            canvas.line(plot_left, y, plot_right, y)
            canvas.setFillColor(_MUTED)
            canvas.setFont("Helvetica", 6)
            canvas.drawRightString(
                plot_left - 4,
                y - 2,
                f"{maximum * ratio:,.0f}",
            )

        canvas.setStrokeColor(self.color)
        canvas.setFillColor(self.color)
        canvas.setLineWidth(1.5)
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
            canvas.circle(point[0], point[1], 2, stroke=0, fill=1)
            previous_point = point

        label_stride = max(1, math.ceil(len(self.labels) / 6))
        canvas.setFillColor(_MUTED)
        canvas.setFont("Helvetica", 6)
        for index, label in enumerate(self.labels):
            if index % label_stride and index != len(self.labels) - 1:
                continue
            x = plot_left + plot_width * index / denominator
            label_text = _safe_text(label)
            if len(label_text) > 10:
                label_text = label_text[-5:]
            canvas.drawCentredString(x, 15, label_text)

        canvas.restoreState()


def _paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(_safe_text(value if value is not None else "")), style)


def _make_kpi_card(kpi: dict[str, Any], styles, width: float) -> Table:
    trend = kpi.get("trend")
    change_color = _GREEN if trend == "up" else _RED if trend == "down" else _MUTED
    change_style = ParagraphStyle(
        "AnalyticsKpiChangeValue",
        parent=styles["kpi_change"],
        textColor=change_color,
    )
    card = Table(
        [
            [_paragraph(kpi.get("label", ""), styles["kpi_label"])],
            [_paragraph(_format_number(kpi.get("value")), styles["kpi_value"])],
            [_paragraph(_kpi_change_text(kpi), change_style)],
        ],
        colWidths=[width],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _PALE),
                ("BOX", (0, 0), (-1, -1), 0.6, _GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return card


def _data_table(
    title: str,
    data: dict[str, Any],
    styles,
    available_width: float,
    limit: int | None = None,
) -> list[Flowable]:
    elements: list[Flowable] = [
        Paragraph(escape(title), styles["section_heading"]),
    ]
    columns = data.get("columns", [])
    rows = data.get("rows", [])
    if limit is not None:
        rows = rows[:limit]
    if not columns or not rows:
        elements.append(Paragraph("No stored data for this section.", styles["body"]))
        elements.append(Spacer(1, 5))
        return elements

    cell_style = styles["table_cell"]
    header_style = styles["table_header"]
    table_data = [
        [_paragraph(column, header_style) for column in columns]
    ] + [
        [_paragraph(row.get(column, ""), cell_style) for column in columns]
        for row in rows
    ]
    column_widths = [available_width / len(columns)] * len(columns)
    if len(columns) > 1:
        column_widths[0] = available_width * 0.32
        remaining_width = available_width - column_widths[0]
        column_widths[1:] = [
            remaining_width / (len(columns) - 1)
        ] * (len(columns) - 1)

    table = Table(
        table_data,
        colWidths=column_widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _PALE]),
                ("GRID", (0, 0), (-1, -1), 0.35, _GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.extend([table, Spacer(1, 8)])
    return elements


def generate_analytics_pdf(
    dashboard: dict[str, Any],
    period: str,
    client_name: str,
) -> bytes:
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"{period.title()} Search and Traffic Report",
        author="SEO Reporting",
    )
    base_styles = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "AnalyticsTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            alignment=TA_LEFT,
            textColor=_NAVY,
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "AnalyticsSubtitle",
            parent=base_styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=_MUTED,
            spaceAfter=5,
        ),
        "section_heading": ParagraphStyle(
            "AnalyticsSection",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=_TEAL,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "AnalyticsBody",
            parent=base_styles["BodyText"],
            fontSize=8,
            leading=11,
            textColor=_NAVY,
        ),
        "kpi_label": ParagraphStyle(
            "AnalyticsKpiLabel",
            parent=base_styles["Normal"],
            fontSize=7,
            leading=9,
            textColor=_MUTED,
            alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "AnalyticsKpiValue",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=_NAVY,
            alignment=TA_CENTER,
        ),
        "kpi_change": ParagraphStyle(
            "AnalyticsKpiChange",
            parent=base_styles["Normal"],
            fontSize=7,
            leading=9,
            textColor=_MUTED,
            alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "AnalyticsTableHeader",
            parent=base_styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=colors.white,
        ),
        "table_cell": ParagraphStyle(
            "AnalyticsTableCell",
            parent=base_styles["Normal"],
            fontSize=7,
            leading=9,
            textColor=_NAVY,
            wordWrap="CJK",
        ),
    }

    period_data = dashboard.get("period", {})
    date_range = (
        f"{period_data.get('start_date', '')} to "
        f"{period_data.get('end_date', '')}"
    )
    comparison_range = (
        f"{period_data.get('comparison_start_date', '')} to "
        f"{period_data.get('comparison_end_date', '')}"
    )
    gsc_source = dashboard.get("sources", {}).get("gsc", {})
    site_url = gsc_source.get("site_url")
    subtitle_parts = [
        f"Prepared for {_safe_text(client_name)}",
        f"Period: {date_range}",
        f"Compared with: {comparison_range}",
    ]
    if site_url:
        subtitle_parts.append(f"Search Console property: {_safe_text(site_url)}")

    story: list[Flowable] = [
        Paragraph(
            f"{period.title()} Search &amp; Traffic Overview",
            styles["title"],
        ),
        Paragraph(escape("  |  ".join(subtitle_parts)), styles["subtitle"]),
        Spacer(1, 7),
        Paragraph("Performance indicators", styles["section_heading"]),
    ]

    kpis = dashboard.get("kpis", [])
    card_width = (document.width - 16) / 3
    cards = [_make_kpi_card(kpi, styles, card_width) for kpi in kpis]
    if cards:
        card_rows = [
            cards[index : index + 3] + [None] * (3 - len(cards[index : index + 3]))
            for index in range(0, len(cards), 3)
        ]
        card_table = Table(
            card_rows,
            colWidths=[card_width] * 3,
            hAlign="LEFT",
        )
        card_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(card_table)
    else:
        story.append(Paragraph("No KPI data is stored for this period.", styles["body"]))

    story.extend(
        [
            Spacer(1, 5),
            Paragraph("Daily trends", styles["section_heading"]),
        ]
    )

    chart_flowables = []
    palette = [
        _TEAL,
        colors.HexColor("#415A9B"),
        colors.HexColor("#C47F17"),
        colors.HexColor("#6C5B7B"),
        _GREEN,
    ]
    for chart_key, chart in dashboard.get("charts", {}).items():
        labels = chart.get("labels", [])
        for dataset_index, dataset in enumerate(chart.get("datasets", [])):
            chart_flowables.append(
                _LineChart(
                    f"{chart_key.replace('_', ' ').title()} — "
                    f"{dataset.get('label', 'Metric')}",
                    labels,
                    dataset.get("data", []),
                    palette[dataset_index % len(palette)],
                    (document.width - 12) / 2,
                )
            )

    if chart_flowables:
        chart_width = (document.width - 12) / 2
        chart_rows = []
        for index in range(0, len(chart_flowables), 2):
            row = chart_flowables[index : index + 2]
            if len(row) == 1:
                row.append(Spacer(chart_width, 1))
            chart_rows.append(row)
        chart_table = Table(
            chart_rows,
            colWidths=[chart_width, chart_width],
            hAlign="LEFT",
        )
        chart_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(chart_table)
    else:
        story.append(Paragraph("No daily trend data is stored for this period.", styles["body"]))

    story.append(PageBreak())
    story.append(Paragraph("Search performance detail", styles["section_heading"]))
    story.extend(
        _data_table(
            "Daily Search Console performance",
            dashboard.get("tables", {}).get("gsc_daily", {}),
            styles,
            document.width,
        )
    )
    story.extend(
        _data_table(
            "Highest-click search queries",
            dashboard.get("tables", {}).get("top_queries", {}),
            styles,
            document.width,
        )
    )
    story.extend(
        _data_table(
            "Highest-click landing pages",
            dashboard.get("tables", {}).get("top_pages", {}),
            styles,
            document.width,
        )
    )
    story.extend(
        _data_table(
            "Daily Analytics performance",
            dashboard.get("tables", {}).get("ga4_daily", {}),
            styles,
            document.width,
        )
    )
    story.extend(
        _data_table(
            "Google Sheets data (first 20 rows)",
            dashboard.get("tables", {}).get("google_sheets", {}),
            styles,
            document.width,
            limit=20,
        )
    )

    def draw_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_GRID)
        canvas.line(doc.leftMargin, 11 * mm, A4[0] - doc.rightMargin, 11 * mm)
        canvas.setFillColor(_MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(doc.leftMargin, 7 * mm, "Generated from stored integration data")
        canvas.drawRightString(A4[0] - doc.rightMargin, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return output.getvalue()
