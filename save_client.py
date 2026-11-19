from app.models.client import Client, Integrations, GSCIntegration
from app.api.v1.routers.client_routes import save_client

client = Client(client_id="client_001", name="Nikhil Ads", website="https://nikhilsads.com/", integrations=Integrations(gsc=GSCIntegration(enabled=True, property_url="https://nikhilsads.com/")))
result = save_client(client)
if result:
    print("Client data saved in DB")