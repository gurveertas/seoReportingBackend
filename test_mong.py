import os
import ssl
import certifi
import pymongo

from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

print("Python SSL:", ssl.OPENSSL_VERSION)
print("PyMongo:", pymongo.version)

uri = os.getenv("MONGO_URI")

client = MongoClient(
    uri,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=10000
)

try:
    print(client.admin.command("ping"))
    print("MongoDB connected successfully!")
except Exception as error:
    print("Connection failed:", repr(error))
finally:
    client.close()