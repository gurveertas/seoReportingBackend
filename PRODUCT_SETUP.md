# Multi-user setup: connect Google, list websites, monthly reports

Any user can now sign up, click **Connect Google account**, see every Search Console
website that Google account can access (with the matching GA4 property pre-selected),
add the ones they want, and get a PDF report for each one every month.

## How it works

1. A user signs in and clicks **Connect Google account** (Websites page or Settings).
2. Google asks for **read-only** access to Search Console, Analytics and Sheets.
3. The backend stores the refresh token **encrypted** (`google_connections`), then lists:
   * Search Console sites (`sites.list`, readable permission levels only)
   * GA4 properties and their web streams (Analytics Admin API)
   and matches GA4 → site by hostname (`google_sites`).
4. The user ticks websites and clicks **Add**. Each becomes a client linked to that
   Google account (`google_connection_id`), with **auto-generate monthly** on by default.
5. Each website's dashboard has a **Monthly reports** panel: pick any completed month →
   fresh data is pulled → PDF saved (MongoDB GridFS) → listed for download.
6. A daily scheduled call generates last month's report for every website with
   auto-monthly on, from the 4th of the month (Search Console lags 2–3 days).
   It skips reports that already exist, so it's safe to call every day.

A user can connect several Google accounts (useful for agencies). Clients added
manually can be linked by importing the matching website from a connected Google account.

## 1. Google Cloud setup (one time, by the project owner)

1. **APIs & Services → Library**: enable
   * Google Search Console API
   * Google Analytics **Admin** API (lists GA4 properties; new requirement)
   * Google Analytics **Data** API
   * Google Sheets API
2. **Google Auth Platform → Branding**: app name, support email, logo, homepage,
   privacy policy and terms URLs, authorized domain(s) (your frontend and backend domains).
3. **Audience**: User type **External**.
4. **Data access → Add scopes**:
   * `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`
   * `.../auth/webmasters.readonly`
   * `.../auth/analytics.readonly`
   * `.../auth/spreadsheets.readonly` (remove it from `SCOPES` in
     `app/integrations/google_oauth.py` if you don't use the Sheets tabs; one fewer
     scope to justify in verification)
5. **Clients → Create client → Web application**.
   Authorized redirect URI (exact):
   `https://<your-backend>/api/v1/integrations/google/callback`
   (and `http://localhost:8000/api/v1/integrations/google/callback` for local dev).
   Copy the client ID and secret into the backend env.

### Testing vs. production (important for monthly reports)

* **Testing**: only test users you list (max 100) can connect, and Google expires
  their access **7 days after consent**, so automatic monthly reports will fail with
  "Google access expired". Fine for trying it out, not for real use.
* **In production**: click **Publish app**. The app requests sensitive scopes, so
  Google will show an "unverified app" warning and cap you at 100 users until you
  complete **verification** (privacy policy, domain ownership in Search Console,
  a short demo video showing how each scope is used). Start this early; it can take
  weeks.

## 2. Backend environment

Copy `.env.example` → `.env` and fill it in. New variables:

| Variable | Purpose |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth web client from step 1.5 |
| `GOOGLE_OAUTH_REDIRECT_URI` | Must exactly match the redirect URI on the client |
| `FRONTEND_URL` | Where users land after Google sign-in |
| `TOKEN_ENCRYPTION_KEY` | Fernet key that encrypts refresh tokens. Generate once and keep it safe. Changing it disconnects everyone |
| `CORS_ORIGINS` | Comma-separated frontend origins |
| `CRON_SECRET` | Protects the scheduler endpoint |
| `NOTIFY_WEBHOOK_URL` | Optional: Slack/Teams webhook for failed scheduled reports |

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend: set `VITE_API_BASE_URL` to the backend's `/api/v1` URL (see `.env`).

> **Cookies across domains.** Login uses an http-only cookie with `SameSite=None`.
> It works today with the frontend on vercel.app and the API on fastapicloud.dev, but
> Safari and future Chrome versions block cross-site cookies. Putting both on one
> domain (e.g. `app.yourdomain.com` + `api.yourdomain.com`) avoids this, and the
> Google callback check (below) relies on the cookie too.

## 3. Schedule the monthly run (pick one)

**Hosted (recommended for FastAPI Cloud):** call this once a day from any cron service
(cron-job.org, GitHub Actions, Google Cloud Scheduler):

```
POST https://<backend>/api/v1/internal/cron/monthly
Header: X-Cron-Secret: <CRON_SECRET>
```

It returns immediately and runs in the background. Add `?wait=true` to get the
per-website result in the response.

**On a PC/server:** run daily with cron or Windows Task Scheduler:

```bash
python -m app.jobs.monthly                    # due reports only
python -m app.jobs.monthly --month 2026-10    # a specific month
python -m app.jobs.monthly --client <id> --month 2026-10 --force   # rebuild one
```

The command exits with code 1 if any report failed. Every attempt is logged in
`report_runs` (status, error, duration, manual/scheduled), and the last failure is
shown in the website's Monthly reports panel. A Search Console or GA4 failure stores
**no** report (no partial PDFs); a Sheets failure only adds a warning.

## 4. New API endpoints (all under `/api/v1`)

| Method & path | What it does |
|---|---|
| `GET /integrations/google/connect?return_to=/sites` | Returns Google consent URL |
| `GET /integrations/google/callback` | Google redirects here; stores connection, syncs sites |
| `GET /integrations/google/connections` | Connected Google accounts |
| `POST /integrations/google/connections/{id}/sync` | Re-list websites & GA4 properties |
| `DELETE /integrations/google/connections/{id}` | Revoke + remove an account |
| `GET /integrations/google/sites` | All websites across accounts (+ GA4 options, already-added flag) |
| `POST /integrations/google/sites/import` | Add selected websites as clients |
| `GET /clients/{id}/reports` | Saved reports + recent runs + latest reportable month |
| `POST /clients/{id}/reports/monthly/generate` | `{ "month": "2026-10" }` pull data, build and save the PDF |
| `GET /clients/{id}/reports/{report_id}/download` | Download a saved PDF |
| `DELETE /clients/{id}/reports/{report_id}` | Delete a saved PDF |
| `GET /reports` | Recent reports across the workspace |
| `PATCH /clients/{id}` | Now also accepts `{ "auto_monthly": true/false }` |
| `GET /clients/{id}/analytics/monthly?month=YYYY-MM` | Dashboard data for any month |
| `POST /internal/cron/monthly` | Scheduler entry point (secret header) |

## 5. Security notes

* Refresh tokens are Fernet-encrypted at rest and never returned by the API.
* The OAuth `state` is a signed, 10-minute token **and** the callback checks that the
  signed-in browser's workspace matches it, so a consent link made in one workspace
  can't attach someone else's Google account to it.
* Every query is scoped by `workspace_id`; users can't see or download other
  workspaces' sites or reports (covered by tests).
* Disconnecting revokes the token at Google. Websites linked to that account stop
  updating (with a clear message) until the account is reconnected; re-adding the
  same site from the Websites page re-links the existing client.
* Re-running a period now **overwrites** stored snapshots instead of duplicating them.

## 6. Tests

```bash
pip install -r requirements-dev.txt
pytest --deselect test_google_integrations.py --deselect test_gsc.py  # those two need real keys
```
