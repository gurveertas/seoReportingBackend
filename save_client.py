import os

from app.models.client import Client, Integrations, GSCIntegration
from app.api.v1.routers.client_routes import save_client

workspace_id = os.getenv("WORKSPACE_ID")
if not workspace_id:
    raise RuntimeError("Set WORKSPACE_ID before running this script.")

client = Client(
    workspace_id=workspace_id,
    name="Nikhil Ads",
    integrations=Integrations(
        gsc=GSCIntegration(
            enabled=True,
            property_url="https://nikhilsads.com/",
        )
    ),
)
result = save_client(client)
if result:
    print(f"Client created with id {result}")