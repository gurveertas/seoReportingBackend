from app.integrations.gsc.client import get_gsc_client
from app.integrations.gsc.service import (
    get_gsc_sites,
    get_search_performance
)
from app.models.gsc import GSCMetrics, GSCDocument, Period
from app.api.v1.routers.gsc_routes import save_gsc_data
from app.reports.gsc_report import generate_gsc_pdf
import os

CREDENTIALS_PATH = "app/integrations/gsc/credentials/service-account.json"

def main():

    # Authenticate
    metrics = []
    service = get_gsc_client(CREDENTIALS_PATH)

    print("Successfully authenticated with Google!")

    # Request 1: Get accessible websites
    sites = get_gsc_sites(service)

    print("\nAccessible websites:")

    for site in sites:
        print(
            f"Website: {site['siteUrl']} | "
            f"Permission: {site['permissionLevel']}"
        )

    if not sites:
        print("\nNo websites accessible to this service account.")
        return

    # Select the first website
    site_url = sites[0]["siteUrl"]

    # Request 2: Get SEO data
    data = get_search_performance(
        service=service,
        site_url=site_url,
        start_date="2026-10-01",
        end_date="2026-10-31"
    )

    print(f"\nSEO data for {site_url}")
    for row in data:
        print(row)
        metrics.append(row["clicks"])
        metrics.append(row["impressions"])
        metrics.append(row["ctr"])
        metrics.append(row["position"])
    # print(metrics)
    workspace_id = os.getenv("WORKSPACE_ID")
    client_id = os.getenv("CLIENT_ID")
    if not workspace_id or not client_id:
        raise RuntimeError("Set WORKSPACE_ID and CLIENT_ID before running this script.")
    gsc_data = GSCDocument(
        workspace_id=workspace_id,
        client_id=client_id,
        property_url="https://nikhilsads.com/",
        metrics=GSCMetrics(clicks=metrics[0], impressions=metrics[1], ctr=metrics[2], position = metrics[3]),
        period=Period(type='weekly', start_date="18-11-2026", end_date="18-11-2026")
    )
    try:
        save_gsc_data(gsc_data)
        generate_gsc_pdf(
        data=gsc_data,
        output_path="reports/nikhilsads_october_2026.pdf"
        )

    except Exception as e:
        print(e)
        

    print(f"\nTotal rows fetched: {len(data)}")


if __name__ == "__main__":
    main()