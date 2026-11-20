# Frontend Workspace and Analytics Guide

Each account is a workspace. A workspace can own multiple client records; each client stores its name and GSC, GA4, and Google Sheets configuration. Client and report routes are scoped by `client_id`, and the backend verifies that the authenticated workspace owns that client.

## API base URL

Configure the backend URL through a frontend environment variable. For example:

```text
VITE_API_BASE_URL=https://your-api-host
```

The examples below assume `API_BASE_URL` does not end with a slash.

## Authentication

The backend authenticates using the HttpOnly `access_token` cookie. JavaScript cannot read this cookie; the browser must send it automatically.

Use `credentials: "include"` for all authentication and client requests:

```js
const response = await fetch(`${API_BASE_URL}/api/v1/auth/login`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username, password }),
});
```

With Axios, set `withCredentials: true`:

```js
axios.get(`${API_BASE_URL}/api/v1/clients/${clientId}/analytics/monthly`, {
  withCredentials: true,
});
```

### Workspace signup

Create the workspace first. Integrations are configured on clients after signup.

```js
const response = await fetch(`${API_BASE_URL}/api/v1/auth/register`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    username: "workspace-owner",
    password: "use-a-strong-password",
    fullname: "Workspace Owner",
  }),
});
```

### Workspace and client endpoints

| Method | Path | Authentication | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/health` | None | Check that the API is reachable |
| `POST` | `/api/v1/auth/register` | None | Create a workspace and sign it in |
| `POST` | `/api/v1/auth/login` | None | Sign in to a workspace |
| `POST` | `/api/v1/auth/logout` | None | Clear the login cookie |
| `GET` | `/api/v1/me` | Required | Return the authenticated workspace profile |
| `PATCH` | `/api/v1/me` | Required | Update workspace profile data |
| `GET` | `/api/v1/clients` | Required | List clients owned by the workspace |
| `POST` | `/api/v1/clients` | Required | Create a client |
| `GET` | `/api/v1/clients/{client_id}` | Required | Load a client's settings |
| `PATCH` | `/api/v1/clients/{client_id}` | Required | Update a client's name and/or integrations |
| `DELETE` | `/api/v1/clients/{client_id}` | Required | Delete a client and its stored integration data |

The workspace signup body contains `username`, `password`, and `fullname`. Integrations belong to clients, not the workspace. Create a client with:

```json
{
  "name": "Acme",
  "integrations": {
    "gsc": { "enabled": true, "property_url": "https://example.com/" },
    "ga4": { "enabled": true, "property_id": "123456789" },
    "google_sheets": { "enabled": false, "property_id": "spreadsheet-id" }
  }
}
```

`POST /api/v1/clients` returns a `client_id`. Use it for that client's settings, integrations, analytics, refresh, and report requests. For `PATCH /api/v1/clients/{client_id}`, send the full `integrations` object if changing integration configuration; it replaces the saved values. Omit it to preserve the current configuration.

`GET /api/v1/me` and its `/api/v1/auth/me` alias return workspace profile data. Use `GET /api/v1/clients` to load each client's name and integrations for the workspace UI. To log out, send `POST /api/v1/auth/logout` with `credentials: "include"`; it clears the HttpOnly cookie even if the session has expired. An unauthenticated or expired session returns `401`.

Each client returned by `GET /api/v1/clients` includes `client_id`, `name`, `integrations`, `created_at`, and `updated_at`.

## Client-scoped data endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/clients/{client_id}/analytics/monthly` | Load this client's monthly view. |
| `GET` | `/api/v1/clients/{client_id}/analytics/weekly` | Load this client's weekly view. |
| `POST` | `/api/v1/clients/{client_id}/analytics/refresh?period=monthly` | Refresh this client's integrations and return database-backed analytics. |
| `POST` | `/api/v1/clients/{client_id}/analytics/refresh?period=weekly` | Same refresh flow for this client's weekly view. |
| `GET` | `/api/v1/clients/{client_id}/gsc/sites` | List Search Console sites for this client. |
| `POST` | `/api/v1/clients/{client_id}/gsc/search-performance` | Fetch and store this client's Search Console data. |
| `POST` | `/api/v1/clients/{client_id}/ga4/report` | Fetch and store this client's GA4 data. |
| `POST` | `/api/v1/clients/{client_id}/google-sheets/values` | Fetch and store this client's Google Sheets data. |
| `GET` | `/api/v1/clients/{client_id}/reports/monthly` | Download this client's monthly PDF. |
| `GET` | `/api/v1/clients/{client_id}/reports/weekly` | Download this client's weekly PDF. |

The monthly view covers the latest completed calendar month and compares it with the previous month. The weekly view covers the latest completed Monday-to-Sunday week and compares it with the previous week. Load the monthly view by default and use the selected client's `client_id` for every data request.

The analytics `GET` routes read stored records for the selected client only; they do not call Google. The refresh `POST` route calls that client's enabled integrations, stores their results with both workspace and client IDs, then rebuilds the dashboard from those records. Its request has **no body**.

The PDF routes are authenticated and read stored data only. Requesting a client-scoped report route generates the PDF and returns it as `application/pdf`. The frontend should keep the returned `Blob`, show a “Report ready” dialog, then let the user click “Save PDF”.

```js
async function generateReport(clientId, period) {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/clients/${clientId}/reports/${period}`,
    { credentials: "include" }
  );
  if (!response.ok) {
    throw new Error("Unable to generate the report.");
  }

  return {
    blob: await response.blob(),
    filename: `seo-report-${period}.pdf`,
  };
}

async function saveGeneratedReport(report) {
  if ("showSaveFilePicker" in window) {
    const handle = await window.showSaveFilePicker({
      suggestedName: report.filename,
      types: [{
        description: "PDF document",
        accept: { "application/pdf": [".pdf"] },
      }],
    });
    const writable = await handle.createWritable();
    await writable.write(report.blob);
    await writable.close();
    return;
  }

  // Fallback: the browser downloads using its configured download behavior.
  const url = URL.createObjectURL(report.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = report.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
```

Call `generateReport(clientId, period)` from the report button, then show the ready dialog with a Save button that calls `saveGeneratedReport(report)` directly from its click handler. Supported browsers then show the native file-location picker. Browsers without the File System Access API use their normal download behavior; to get a save-location prompt there, the user may need to enable “Ask where to save each file” in browser settings. A website cannot force that native prompt in every browser.

Example:

```js
async function loadAnalytics(clientId, period = "monthly") {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/clients/${clientId}/analytics/${period}`,
    { credentials: "include" }
  );

  if (response.status === 401) {
    // Handle an expired or missing login.
    throw new Error("Please sign in again.");
  }
  if (!response.ok) {
    throw new Error("Unable to load analytics.");
  }

  return response.json();
}
```

For the refresh button, use the currently selected period. The response already contains the refreshed dashboard; use it to update the page rather than making an immediate extra `GET`:

```js
async function refreshAnalytics(clientId, period) {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/clients/${clientId}/analytics/refresh?period=${period}`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  if (!response.ok) {
    throw new Error("Unable to refresh analytics.");
  }

  return response.json();
}
```

## Dashboard response

Both `GET` routes and the refresh `POST` return the dashboard fields below. The refresh `POST` additionally returns a `refresh` object.

```json
{
  "client": {
    "client_id": "66aabbccddeeff0011223344",
    "name": "Acme"
  },
  "period": {
    "mode": "monthly",
    "start_date": "2026-10-01",
    "end_date": "2026-10-31",
    "comparison_start_date": "2026-09-01",
    "comparison_end_date": "2026-09-30"
  },
  "sources": {
    "gsc": {
      "status": "available",
      "fetched_at": "2026-11-19T12:00:00Z",
      "site_url": "https://example.com/"
    },
    "ga4": {
      "status": "available",
      "fetched_at": "2026-11-19T12:00:00Z"
    },
    "google_sheets": {
      "status": "available",
      "fetched_at": "2026-11-19T12:00:00Z"
    }
  },
  "kpis": [
    {
      "key": "gsc_clicks",
      "label": "Search clicks",
      "value": 1320,
      "previous_value": 1190,
      "change": 10.92,
      "change_unit": "percent",
      "trend": "up"
    },
    {
      "key": "gsc_ctr",
      "label": "Click-through rate",
      "value": 4.05,
      "previous_value": 3.8,
      "change": 0.25,
      "change_unit": "percentage_points",
      "trend": "up"
    },
    {
      "key": "gsc_position",
      "label": "Average position",
      "value": 14.2,
      "previous_value": 15.1,
      "change": 0.9,
      "change_unit": "positions",
      "trend": "up"
    }
  ],
  "charts": {
    "gsc_daily": {
      "type": "line",
      "labels": ["2026-10-01", "2026-10-02"],
      "datasets": [
        { "label": "clicks", "data": [21, 24] },
        { "label": "impressions", "data": [420, 465] }
      ]
    },
    "ga4_daily": {
      "type": "line",
      "labels": ["2026-10-01", "2026-10-02"],
      "datasets": [
        { "label": "totalUsers", "data": [34, 39] },
        { "label": "sessions", "data": [48, 51] },
        { "label": "screenPageViews", "data": [105, 117] }
      ]
    }
  },
  "tables": {
    "gsc_daily": {
      "columns": [
        "date",
        "clicks",
        "impressions",
        "ctr_percent",
        "position"
      ],
      "rows": [
        {
          "date": "2026-10-01",
          "clicks": 21,
          "impressions": 420,
          "ctr_percent": 5.0,
          "position": 14.2
        }
      ]
    },
    "ga4_daily": {
      "columns": ["date", "totalUsers", "sessions", "screenPageViews"],
      "rows": [
        {
          "date": "2026-10-01",
          "totalUsers": 34,
          "sessions": 48,
          "screenPageViews": 105
        }
      ]
    },
    "top_queries": {
      "columns": [
        "query",
        "clicks",
        "impressions",
        "ctr_percent",
        "position"
      ],
      "rows": [
        {
          "query": "example search",
          "clicks": 21,
          "impressions": 420,
          "ctr_percent": 5.0,
          "position": 14.2
        }
      ]
    },
    "top_pages": {
      "columns": [
        "page",
        "clicks",
        "impressions",
        "ctr_percent",
        "position"
      ],
      "rows": []
    },
    "google_sheets": {
      "columns": ["Leads", "Month"],
      "rows": [{ "Leads": 46, "Month": "October" }]
    }
  }
}
```

The sample values above are illustrative. Render the `charts` object using the charting library chosen by the frontend. `labels` provides the x-axis values; each `datasets[].data` array aligns by index with those labels. The `tables` objects can be rendered as columns plus row objects.

### KPI interpretation

- `change_unit: "percent"`: `change` is percentage change.
- `change_unit: "percentage_points"`: `change` is the difference in percentage points, used for CTR.
- `change_unit: "positions"`: positive `change` means average position improved (the numeric position became lower).
- `trend` can be `"up"`, `"down"`, `"steady"`, or `"unavailable"`.
- `value`, `previous_value`, or `change` can be `null` when the required period data is not stored.

### Empty and partial data

- A source can have `status: "no_data"` until a refresh has stored a matching snapshot.
- Empty data is represented by empty `labels`, `datasets[].data`, or table `rows`; do not treat it as an error or fabricate zero values.
- A refresh response's `refresh` object reports each integration independently. A source may be `"refreshed"`, `"not_configured"`, or `"error"`; display available sources even if another source failed.

Example refresh status:

```json
{
  "refresh": {
    "ga4": { "status": "refreshed", "record_ids": ["..."] },
    "gsc": { "status": "refreshed", "record_ids": ["..."] },
    "google_sheets": { "status": "refreshed", "record_id": "..." }
  }
}
```

Google Sheets uses the default range `A1:J100`. The first row is treated as the table header. Its current data is shown as a table; it is not automatically converted to a chart because the sheet's column meanings are not configured.

## Suggested dashboard behavior

1. On page load, fetch `/api/v1/clients` and let the user select a client.
2. Load that client's monthly `GET` route and select Monthly in the UI.
3. On a Weekly/Monthly toggle, call that client's route for the selected mode.
4. On Refresh, call the client-scoped refresh `POST` with the selected period, then render its returned dashboard.
5. Show `period.start_date`–`period.end_date` and the comparison dates in the UI.
6. Handle `401` by returning the workspace user to login. Show a useful empty state for `no_data`.
