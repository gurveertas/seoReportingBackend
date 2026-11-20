"""Discover every website a connected Google account can report on.

Search Console sites come from `sites.list`; GA4 properties come from the
Analytics Admin API (`accountSummaries.list` + each property's web data streams).
GA4 properties are matched to sites by hostname so most sites arrive with
their Analytics property already selected.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from googleapiclient.discovery import build

from app.database.connection import get_database
from app.integrations.google_oauth import CONNECTIONS, credentials_for_connection

logger = logging.getLogger(__name__)

SITES = "google_sites"
# Search Console permission levels that can read performance data.
READABLE_PERMISSIONS = {"siteOwner", "siteFullUser", "siteRestrictedUser"}
MAX_GA4_PROPERTIES = 300


def _strip_www(host: str) -> str:
    host = host.lower().strip(".")
    return host[4:] if host.startswith("www.") else host


def site_host(site_url: str) -> tuple[str, bool]:
    """Return (host, is_domain_property) for a Search Console site URL."""
    if site_url.startswith("sc-domain:"):
        return _strip_www(site_url.removeprefix("sc-domain:")), True
    return _strip_www(urlparse(site_url).hostname or site_url), False


def host_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    if "://" not in uri:
        uri = f"https://{uri}"
    host = urlparse(uri).hostname
    return _strip_www(host) if host else None


def ga4_matches_site(site_url: str, stream_hosts: list[str]) -> bool:
    host, is_domain = site_host(site_url)
    for stream_host in stream_hosts:
        if stream_host == host:
            return True
        if is_domain and stream_host.endswith(f".{host}"):
            return True
    return False


def display_name_for_site(site_url: str) -> str:
    host, _ = site_host(site_url)
    return host


def list_gsc_sites(credentials) -> list[dict[str, Any]]:
    service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
    entries = service.sites().list().execute().get("siteEntry", [])
    return [entry for entry in entries if entry.get("permissionLevel") in READABLE_PERMISSIONS]


def list_ga4_properties(credentials) -> list[dict[str, Any]]:
    admin = build("analyticsadmin", "v1beta", credentials=credentials, cache_discovery=False)
    properties: list[dict[str, Any]] = []
    page_token = None
    while True:
        response = admin.accountSummaries().list(pageSize=200, pageToken=page_token).execute()
        for account in response.get("accountSummaries", []):
            for prop in account.get("propertySummaries", []):
                properties.append(
                    {
                        "property_id": prop["property"].split("/")[-1],
                        "display_name": prop.get("displayName"),
                        "account_name": account.get("displayName"),
                        "stream_hosts": [],
                    }
                )
        page_token = response.get("nextPageToken")
        if not page_token or len(properties) >= MAX_GA4_PROPERTIES:
            break

    properties = properties[:MAX_GA4_PROPERTIES]

    def load_streams(prop: dict[str, Any]) -> None:
        # One service object per thread: googleapiclient objects are not thread-safe.
        local_admin = build("analyticsadmin", "v1beta", credentials=credentials, cache_discovery=False)
        try:
            streams = (
                local_admin.properties()
                .dataStreams()
                .list(parent=f"properties/{prop['property_id']}", pageSize=50)
                .execute()
                .get("dataStreams", [])
            )
        except Exception:  # A single unreadable property must not fail the whole sync.
            logger.warning("Could not read data streams for GA4 property %s", prop["property_id"])
            return
        hosts = {
            host_from_uri((stream.get("webStreamData") or {}).get("defaultUri"))
            for stream in streams
            if stream.get("type") == "WEB_DATA_STREAM"
        }
        prop["stream_hosts"] = sorted(host for host in hosts if host)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(load_streams, properties))
    return properties


def sync_connection(connection: dict[str, Any]) -> dict[str, Any]:
    """Refresh the cached list of sites and GA4 properties for one connection."""
    credentials = credentials_for_connection(connection)
    sites = list_gsc_sites(credentials)
    try:
        ga4_properties = list_ga4_properties(credentials)
        ga4_error = None
    except Exception as error:  # e.g. the account has no Analytics access at all
        logger.warning("GA4 discovery failed for connection %s: %s", connection["_id"], error)
        ga4_properties = []
        ga4_error = "Google Analytics properties could not be listed for this account."

    database = get_database()
    now = datetime.now(timezone.utc)
    workspace_id = connection["workspace_id"]
    connection_id = str(connection["_id"])
    seen_urls = []
    for entry in sites:
        site_url = entry["siteUrl"]
        seen_urls.append(site_url)
        suggestions = [
            {k: prop[k] for k in ("property_id", "display_name", "account_name")}
            for prop in ga4_properties
            if ga4_matches_site(site_url, prop["stream_hosts"])
        ]
        database[SITES].update_one(
            {"workspace_id": workspace_id, "connection_id": connection_id, "site_url": site_url},
            {
                "$set": {
                    "permission_level": entry.get("permissionLevel"),
                    "display_name": display_name_for_site(site_url),
                    "ga4_suggestions": suggestions,
                    "synced_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
    database[SITES].delete_many(
        {"workspace_id": workspace_id, "connection_id": connection_id, "site_url": {"$nin": seen_urls}}
    )
    database[CONNECTIONS].update_one(
        {"_id": connection["_id"]},
        {
            "$set": {
                "ga4_properties": [
                    {k: prop[k] for k in ("property_id", "display_name", "account_name", "stream_hosts")}
                    for prop in ga4_properties
                ],
                "ga4_error": ga4_error,
                "sites_synced_at": now,
                "status": "active",
                "last_error": None,
            }
        },
    )
    return {"sites": len(sites), "ga4_properties": len(ga4_properties), "ga4_error": ga4_error}
