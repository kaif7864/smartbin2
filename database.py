from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL")

client = MongoClient(MONGO_URL)
db = client["smart_dustbin"]

POINTS_MAP = {
    "cardboard": 10,
    "glass":     15,
    "metal":     20,
    "paper":     8,
    "plastic":   12,
    "trash":     2,
}