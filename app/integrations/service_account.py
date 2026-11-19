import json
import os

from google.oauth2 import service_account


def get_service_account_credentials(
    credentials_path: str | None,
    json_environment_variable: str,
    scopes: list[str],
):
    service_account_json = os.getenv(json_environment_variable)
    if service_account_json:
        try:
            service_account_info = json.loads(service_account_json)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{json_environment_variable} must contain valid JSON."
            ) from error

        return service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=scopes,
        )

    if credentials_path:
        return service_account.Credentials.from_service_account_file(
            credentials_path,
            scopes=scopes,
        )

    raise ValueError(
        f"Set {json_environment_variable} or provide a credentials file path."
    )
