def get_sheet_data(
    service,
    spreadsheet_id: str,
    range_name: str,
):
    response = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        )
        .execute()
    )

    return response.get("values", [])