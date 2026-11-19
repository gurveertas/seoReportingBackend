
import os
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak
)


def generate_gsc_pdf(data, output_path="reports/seo_report.pdf"):

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    metrics = data.metrics
    period = data.period

    # -------------------------
    # 1. Generate charts
    # -------------------------

    chart_dir = "reports/charts"
    os.makedirs(chart_dir, exist_ok=True)

    clicks_chart = os.path.join(chart_dir, "clicks.png")
    impressions_chart = os.path.join(chart_dir, "impressions.png")

    # Clicks chart
    plt.figure(figsize=(6, 3))

    plt.bar(
        ["Organic Clicks"],
        [metrics.clicks]
    )

    plt.title("Organic Search Clicks")
    plt.ylabel("Clicks")

    plt.tight_layout()
    plt.savefig(clicks_chart, dpi=200)
    plt.close()

    # Impressions chart
    plt.figure(figsize=(6, 3))

    plt.bar(
        ["Impressions"],
        [metrics.impressions]
    )

    plt.title("Search Impressions")
    plt.ylabel("Impressions")

    plt.tight_layout()
    plt.savefig(impressions_chart, dpi=200)
    plt.close()

    # -------------------------
    # 2. Create PDF
    # -------------------------

    pdf = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=10
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#2563EB"),
        spaceBefore=15,
        spaceAfter=10
    )

    normal_style = styles["Normal"]

    content = []

    # -------------------------
    # 3. Report Header
    # -------------------------

    content.append(
        Paragraph("SEO PERFORMANCE REPORT", title_style)
    )

    content.append(
        Paragraph(
            f"<b>Website:</b> {data.property_url}",
            normal_style
        )
    )

    content.append(
        Paragraph(
            f"<b>Reporting Period:</b> "
            f"{period.start_date} to {period.end_date}",
            normal_style
        )
    )

    content.append(Spacer(1, 20))

    # -------------------------
    # 4. KPI Table
    # -------------------------

    kpi_data = [
        ["CLICKS", "IMPRESSIONS", "CTR", "AVG POSITION"],
        [
            str(metrics.clicks),
            str(metrics.impressions),
            f"{metrics.ctr * 100:.2f}%",
            f"{metrics.position:.2f}"
        ]
    ]

    kpi_table = Table(
        kpi_data,
        colWidths=[125, 125, 125, 125]
    )

    kpi_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             colors.HexColor("#1F2937")),

            ("TEXTCOLOR", (0, 0), (-1, 0),
             colors.white),

            ("BACKGROUND", (0, 1), (-1, 1),
             colors.HexColor("#F3F4F6")),

            ("ALIGN", (0, 0), (-1, -1), "CENTER"),

            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),

            ("FONTSIZE", (0, 0), (-1, 0), 9),

            ("FONTSIZE", (0, 1), (-1, 1), 16),

            ("TOPPADDING", (0, 0), (-1, -1), 14),

            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),

            ("BOX", (0, 0), (-1, -1), 0.5,
             colors.HexColor("#D1D5DB")),

            ("INNERGRID", (0, 0), (-1, -1), 0.5,
             colors.HexColor("#D1D5DB"))
        ])
    )

    content.append(kpi_table)

    content.append(Spacer(1, 20))

    # -------------------------
    # 5. Performance Charts
    # -------------------------

    content.append(
        Paragraph("Performance Overview", heading_style)
    )

    content.append(
        Image(clicks_chart, width=220, height=150)
    )

    content.append(
        Image(impressions_chart, width=220, height=150)
    )

    content.append(Spacer(1, 15))

    # -------------------------
    # 6. Basic Insights
    # -------------------------

    content.append(
        Paragraph("SEO Insights", heading_style)
    )

    ctr_percent = metrics.ctr * 100

    insights = [
        f"The website received {metrics.clicks} organic clicks "
        f"during the reporting period.",

        f"The website appeared {metrics.impressions} times "
        f"in Google Search results.",

        f"The average click-through rate was {ctr_percent:.2f}%.",

        f"The average search position was "
        f"{metrics.position:.2f}."
    ]

    for insight in insights:
        content.append(
            Paragraph(f"• {insight}", normal_style)
        )
        content.append(Spacer(1, 6))

    # -------------------------
    # 7. Footer information
    # -------------------------

    content.append(Spacer(1, 20))

    content.append(
        Paragraph(
            "Generated automatically using Google Search Console data.",
            styles["Italic"]
        )
    )

    # -------------------------
    # 8. Build PDF
    # -------------------------

    pdf.build(content)

    print(f"PDF report generated: {output_path}")

    return output_path
