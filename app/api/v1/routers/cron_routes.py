"""Endpoint for a hosted scheduler (cron-job.org, GitHub Actions, Cloud Scheduler...).

Call daily:  POST /api/v1/internal/cron/monthly   header  X-Cron-Secret: <CRON_SECRET>
Add ?wait=true to run in the request instead of in the background.
"""

import os
import secrets

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status

from app.jobs.monthly import run_monthly_reports

cron_router = APIRouter(include_in_schema=False)


@cron_router.post("/monthly")
def trigger_monthly_reports(
    background_tasks: BackgroundTasks,
    wait: bool = False,
    x_cron_secret: str | None = Header(default=None),
):
    expected = os.getenv("CRON_SECRET")
    if not expected or not x_cron_secret or not secrets.compare_digest(expected, x_cron_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret.")
    if wait:
        return run_monthly_reports()
    background_tasks.add_task(run_monthly_reports)
    return {"status": "accepted"}
