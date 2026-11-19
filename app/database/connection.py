import os
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI,tls=True, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=15000)

DB_NAME = os.getenv("DB_NAME", "seo_reporting")

db = client[DB_NAME]

def get_database():
    return db

def check_connection():
    try:
        client.admin.command("ping")
        print("Connected to MongoDB successfully!")
        return True
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return False