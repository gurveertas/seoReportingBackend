
import json
import os

from app.integrations.ga4.client import get_ga4_client
from app.integrations.ga4.service import get_ga4_report

from app.integrations.googleSheets.client import get_sheets_client
from app.integrations.googleSheets.service import get_sheet_data


# ==========================
# CONFIGURATION
# ==========================

GA4_CREDENTIALS = "app/integrations/ga4/credentials/service-account.json"
SHEETS_CREDENTIALS = "app/integrations/googleSheets/credentials/service-account.json"

GA4_PROPERTY_ID = "565126740"

SPREADSHEET_ID = "1X0yjGxLbbb6ThX6aVT3m5Jyl5S8xikuZrhWtHRomjS0"
SHEET_RANGE = "Sheet1!A1:F20"


# ==========================
# TEST GA4
# ==========================

def test_ga4():

    print("\n========== TESTING GA4 ==========\n")

    client = get_ga4_client(GA4_CREDENTIALS)

    report = get_ga4_report(
        client=client,
        property_id=GA4_PROPERTY_ID,
        start_date="7daysAgo",
        end_date="yesterday",
        dimensions=["date"],
        metrics=[
            "totalUsers",
            "sessions",
            "screenPageViews",
        ],
    )

    parsed_data = parse_ga4_report(report)

    print("GA4 connection successful!")
    print(f"Rows received: {len(parsed_data)}")

    print(json.dumps(parsed_data, indent=4))

    return parsed_data


# ==========================
# TEST GOOGLE SHEETS
# ==========================

def test_google_sheets():

    print("\n========== TESTING GOOGLE SHEETS ==========\n")

    client = get_sheets_client(SHEETS_CREDENTIALS)

    data = get_sheet_data(
        service=client,
        spreadsheet_id=SPREADSHEET_ID,
        range_name=SHEET_RANGE,
    )

    print("Google Sheets connection successful!")
    print(f"Rows received: {len(data)}")

    print(json.dumps(data, indent=4))

    return data


# ==========================
# RUN TESTS
# ==========================

if __name__ == "__main__":

    try:
        test_ga4()
    except Exception as e:
        print(f"\nGA4 TEST FAILED: {e}")

    try:
        test_google_sheets()
    except Exception as e:
        print(f"\nGOOGLE SHEETS TEST FAILED: {e}")
