"""Generate last month's report for every website with auto-monthly turned on.

Safe to run every day: it only acts from the 4th of the month (Search Console
data lags 2-3 days) and skips websites that already have that month's report.

Run it any of these ways:
  * python -m app.jobs.monthly                 (cron / Windows Task Scheduler)
  * python -m app.jobs.monthly --month 2026-10 --force
  * POST /api/v1/internal/cron/monthly with header X-Cron-Secret (hosted cron)
"""

import argparse
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.database.connection import get_database
from app.reports.storage import REPORTS, ReportGenerationError, generate_monthly_report

logger = logging.getLogger(__name__)
LOCKS = "job_locks"
LOCK_TTL = timedelta(hours=2)


def _acquire_lock(name: str) -> bool:
    now = datetime.now(timezone.utc)
    try:
        result = get_database()[LOCKS].find_one_and_update(
            {"_id": name, "$or": [{"expires_at": {"$lt": now}}, {"expires_at": {"$exists": False}}]},
            {"$set": {"expires_at": now + LOCK_TTL, "started_at": now}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return result is not None
    except DuplicateKeyError:
        return False  # Another run holds an unexpired lock.


def _release_lock(name: str) -> None:
    get_database()[LOCKS].delete_one({"_id": name})


def run_monthly_reports(
    today: date | None = None,
    month_start: date | None = None,
    client_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    from app.api.v1.routers.analytics_routes import latest_reportable_month

    today = today or datetime.now(timezone.utc).date()
    if month_start is None:
        if today.day < 4 and not force:
            return {"status": "skipped", "reason": "Waiting until the 4th for Search Console data.", "results": []}
        month_start = latest_reportable_month(today)
    month = f"{month_start:%Y-%m}"

    lock_name = f"monthly-{month}"
    if not _acquire_lock(lock_name):
        return {"status": "skipped", "reason": "Another run is already in progress.", "month": month, "results": []}

    database = get_database()
    query: dict[str, Any] = {"auto_monthly": True}
    if client_id:
        query = {"_id": ObjectId(client_id)}
    results = []
    try:
        for client in database["clients"].find(query, {"workspace_id": 1, "name": 1}):
            cid = str(client["_id"])
            workspace_id = client["workspace_id"]
            already = database[REPORTS].find_one(
                {"workspace_id": workspace_id, "client_id": cid, "period": "monthly", "month": month}
            )
            if already and not force:
                results.append({"client_id": cid, "name": client.get("name"), "status": "exists"})
                continue
            try:
                report = generate_monthly_report(workspace_id, cid, month_start, refresh=True, trigger="scheduled")
                results.append({"client_id": cid, "name": client.get("name"), "status": "generated", "report_id": report["report_id"]})
            except ReportGenerationError as error:
                results.append({"client_id": cid, "name": client.get("name"), "status": "failed", "error": str(error)})
            except Exception as error:  # Keep going for the other websites.
                logger.exception("Monthly report failed for %s", cid)
                results.append({"client_id": cid, "name": client.get("name"), "status": "failed", "error": error.__class__.__name__})
    finally:
        _release_lock(lock_name)

    summary = {
        "generated": sum(r["status"] == "generated" for r in results),
        "failed": sum(r["status"] == "failed" for r in results),
        "existing": sum(r["status"] == "exists" for r in results),
    }
    return {"status": "done", "month": month, "summary": summary, "results": results}


def main() -> None:
    from app.api.v1.routers.analytics_routes import parse_month

    parser = argparse.ArgumentParser(description="Generate monthly SEO reports.")
    parser.add_argument("--month", help="YYYY-MM (default: latest complete month)")
    parser.add_argument("--client", help="Only this client id (ignores auto_monthly)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if a report exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = run_monthly_reports(month_start=parse_month(args.month), client_id=args.client, force=args.force)
    print(result.get("month"), result.get("summary") or result.get("reason"))
    for row in result["results"]:
        print(f"  {row['status']:<9} {row.get('name')}  {row.get('error', '')}")
    if result.get("summary", {}).get("failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
