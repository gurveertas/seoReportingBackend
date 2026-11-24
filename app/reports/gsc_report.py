from html import escape
from pathlib import Path

from app.reports.formatting import report_number, report_position
from app.reports.pagespeed import pagespeed_section

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle


_NAVY = colors.HexColor("#102A43")
_TEAL = colors.HexColor("#0F766E")
_BLUE = colors.HexColor("#3563A9")
_MUTED = colors.HexColor("#526477")
_GRID = colors.HexColor("#D7E1E9")
_PALE = colors.HexColor("#F3F7FA")


def _metric_chart(value, label, width, color):
    drawing = Drawing(width, 205)
    chart = VerticalBarChart()
    chart.x = 45
    chart.y = 24
    chart.width = width - 59
    chart.height = 165
    chart.data = [(value,)]
    chart.bars[0].fillColor = color
    chart.bars[0].strokeColor = None
    chart.categoryAxis.categoryNames = [label]
    chart.categoryAxis.labels.fontSize = 9
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(1, value) * 1.1
    if value == 0:
        chart.valueAxis.valueMax = 1
        chart.valueAxis.valueStep = 1
    chart.valueAxis.labels.fontSize = 8
    chart.valueAxis.labels.fillColor = _MUTED
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.gridStrokeColor = _GRID
    drawing.add(chart)
    return drawing


def generate_gsc_pdf(data, output_path="reports/seo_report.pdf"):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    metrics = data.metrics
    period = data.period
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=37,
        leftMargin=37,
        topMargin=45,
        bottomMargin=43,
        title="SEO Performance Report",
    )
    # SimpleDocTemplate uses a 6 pt inset at each edge of its frame.
    width = document.width - 12
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle", parent=styles["Heading1"], textColor=_NAVY,
        fontSize=26, leading=31, spaceAfter=8,
    )
    heading = ParagraphStyle(
        "ReportHeading", parent=styles["Heading2"], textColor=_NAVY,
        fontSize=13, leading=16, spaceBefore=18, spaceAfter=7,
    )
    body = ParagraphStyle(
        "ReportBody", parent=styles["Normal"], textColor=_MUTED,
        fontSize=10.5, leading=16, spaceAfter=14,
    )

    clicks = f"{metrics.clicks:,}"
    impressions = f"{metrics.impressions:,}"
    ctr = f"{report_number(metrics.ctr * 100)}%"
    position = report_position(metrics.position)
    kpis = Table(
        [
            ["Clicks", "Impressions", "Click-through rate", "Average position"],
            [clicks, impressions, ctr, position],
        ],
        colWidths=[width / 4] * 4,
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
            ("BACKGROUND", (0, 1), (-1, 1), _PALE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("TEXTCOLOR", (0, 1), (-1, 1), _NAVY),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("FONTSIZE", (0, 1), (-1, 1), 16),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, _GRID),
        ]),
    )

    gutter = 8
    chart_width = (width - gutter) / 2
    charts = Table(
        [[
            _metric_chart(metrics.clicks, "Organic clicks", chart_width, _TEAL),
            "",
            _metric_chart(metrics.impressions, "Search impressions", chart_width, _BLUE),
        ]],
        colWidths=[chart_width, gutter, chart_width],
        style=TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("BOX", (0, 0), (0, 0), 0.5, _GRID),
            ("BOX", (2, 0), (2, 0), 0.5, _GRID),
        ]),
    )

    story = [
        Paragraph("SEO Performance Report", title),
        Paragraph(
            f"<b>Website</b>  {escape(str(data.property_url))}<br/>"
            f"<b>Reporting period</b>  {escape(str(period.start_date))} to "
            f"{escape(str(period.end_date))}",
            body,
        ),
        kpis,
        Paragraph("Performance overview", heading),
        charts,
        Paragraph("SEO insights", heading),
        Paragraph(
            f"The website received {clicks} organic clicks from {impressions} "
            f"Google Search impressions. The click-through rate was {ctr} "
            f"and the average search position was {position}.",
            body,
        ),
    ]

    story.extend(pagespeed_section(data.property_url, heading, body))

    def draw_footer(canvas, doc):
        left = doc.leftMargin + 6
        canvas.saveState()
        canvas.setStrokeColor(_GRID)
        canvas.line(left, 31, left + width, 31)
        canvas.setFillColor(_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(left, 21, "Source: Google Search Console")
        canvas.drawRightString(left + width, 21, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return output_path
