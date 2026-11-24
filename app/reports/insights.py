import json
import logging
import math
import os

import requests


from app.reports.formatting import report_number, report_position

logger = logging.getLogger(__name__)

# Each supported KPI has a defined scope and direction of improvement.
_METRICS = {
    "gsc_clicks": ("Visibility", "Organic search clicks"),
    "gsc_impressions": ("Visibility", "Search impressions"),
    "gsc_ctr": ("Visibility", "Search click-through rate"),
    "gsc_position": ("Rankings", "Average search position"),
    "ga4_totalUsers": ("Audience", "Website users"),
    "ga4_sessions": ("Traffic", "Website sessions"),
    "ga4_screenPageViews": ("Engagement", "Page views"),
}


def report_signals(kpis, hide_comparison, token):
    signals = {}
    for kpi in kpis:
        key = kpi.get("key")
        current = kpi.get("value")
        if key not in _METRICS or not isinstance(current, (int, float)) or not math.isfinite(current):
            continue
        previous = kpi.get("previous_value")
        unit = "%" if key == "gsc_ctr" else ""
        formatter = report_position if key == "gsc_position" else report_number
        value = f"{formatter(current)}{unit}"
        category, title = _METRICS[key]
        if hide_comparison:
            if current <= 0:
                continue
            fact = f"{value} in the reporting period."
        else:
            if not isinstance(previous, (int, float)) or not math.isfinite(previous):
                continue
            improved = current < previous if key == "gsc_position" else current > previous
            if not improved or (key == "gsc_position" and min(previous, current) <= 0):
                continue
            if key == "gsc_position" and formatter(previous) == formatter(current):
                fact = f"Average position improved by less than 0.1 to {value}."
            elif formatter(previous) == formatter(current):
                continue
            else:
                fact = f"Improved from {formatter(previous)}{unit} to {value}."
        signals[key] = {"category": category, "title": title, "fact": fact}

    if not signals or not token:
        return list(signals.values())

    properties = {"metric": {"type": "string", "enum": list(signals)}, "meaning": {"type": "string"}}
    schema = {"type": "object", "additionalProperties": False, "required": ["signals"],
              "properties": {"signals": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False,
                  "properties": properties, "required": list(properties),
              }}}}
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": os.getenv("OPENAI_REPORT_MODEL") or "gpt-4o-mini",
                "store": False,
                "instructions": (
                    "Choose up to four distinct, most informative SEO signals from these verified facts. "
                    "For each explain what the metric means to the client in one short sentence. "
                    "Use no numbers, predictions, causal claims or claims about other metrics. "
                    "GA4 metrics cover all channels. Do not claim a change unless the fact states one."
                ),
                "input": json.dumps(signals),
                "text": {"format": {"type": "json_schema", "name": "report_signals",
                                    "strict": True, "schema": schema}},
            },
            timeout=(4, 20),
        )
        response.raise_for_status()
        result = response.json()
        output = next(part["text"] for item in result["output"] for part in item.get("content", [])
                      if part.get("type") == "output_text")
        selected = {}
        for item in json.loads(output)["signals"]:
            key = item["metric"]
            meaning = item["meaning"].strip()
            if key in signals and meaning and len(meaning) <= 220 and not any(c.isdigit() for c in meaning):
                selected[key] = dict(signals[key], meaning=meaning)
        if selected:
            return list(selected.values())[:4]
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        logger.warning("OpenAI report insights unavailable; using verified KPI facts.")
    return list(signals.values())
