import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.connection import get_database, check_connection
from app.api.v1.router import api_router

# from integrations.gsc.client import get_gsc_client
# from integrations.gsc.service import get_search_performance


# def get_gsc_report(db):
#     service = get_gsc_client("./integrations/gsc/credentials/service-account.json")
#     sites = service.sites().execute()
#     print(sites)
#     site_url = input("Enter client id : ")
#     db
#     result = get_search_performance(service,  )

app = FastAPI()
_default_origins = 'http://localhost:5174,http://localhost:5173,https://forma-tas.vercel.app'
origins = [o.strip() for o in os.getenv('CORS_ORIGINS', _default_origins).split(',') if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_headers=['*'], allow_methods=['*'])
app.include_router(api_router, prefix="/api/v1")

def main():
    if not check_connection():
        print("Exiting due to database connection failure.")
    try:
        db = get_database()
    except Exception as e:
        print("Error connecting to db in main.py : ", e)
    

if __name__ == "__main__":
    main()