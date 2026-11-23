import os
from html import escape

import requests
from reportlab.platypus import Paragraph


def pagespeed_section(property_url, heading_style, body_style):
    """Build a point-in-time mobile Lighthouse summary for a report."""
    section = [Paragraph("PageSpeed Insights", heading_style)]
    key = os.getenv("PAGESPEED_API_KEY") or os.getenv("GOOGLE_API_KEY")
    url = str(property_url or "").strip()
    if url.startswith("sc-domain:"):
        url = "https://" + url.removeprefix("sc-domain:") + "/"
    if not key or not url.startswith(("https://", "http://")):
        section.append(Paragraph("Mobile audit unavailable for this report.", body_style))
        return section

    try:
        response = requests.get(
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            params={"url": url, "strategy": "mobile", "category": "performance", "key": key},
            timeout=(5, 60),
        )
        response.raise_for_status()
        result = response.json()["lighthouseResult"]
        if result.get("runtimeError"):
            raise ValueError("Incomplete Lighthouse audit")
        score = result["categories"]["performance"]["score"]
        if not isinstance(score, (int, float)) or not 0 <= score <= 1:
            raise ValueError("Missing performance score")
    except (requests.RequestException, KeyError, ValueError, TypeError):
        section.append(Paragraph("The mobile audit was unavailable when this report was generated.", body_style))
        return section

    tested_url = escape(str(result.get("finalUrl") or url))
    timestamp = escape(str(result.get("fetchTime") or ""))
    section.append(Paragraph(f"Mobile Lighthouse audit &bull; {tested_url} {timestamp}", body_style))
    metrics = [f"<b>Performance</b> {round(score * 100)}/100"]
    for audit, label in (
        ("largest-contentful-paint", "Largest contentful paint"),
        ("total-blocking-time", "Total blocking time"),
        ("cumulative-layout-shift", "Cumulative layout shift"),
    ):
        value = result.get("audits", {}).get(audit, {}).get("displayValue")
        if value:
            metrics.append(f"<b>{label}</b> {escape(str(value))}")
    section.append(Paragraph(" &bull; ".join(metrics), body_style))
    return section
