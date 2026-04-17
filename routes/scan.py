from fastapi import APIRouter
from database import db
from datetime import datetime

router = APIRouter()

@router.post("/scan")
def scan_garbage(data: dict):
    user_id = data["user_id"]

    user = db.users.find_one({"user_id": user_id})

    if not user:
        return {"error": "Invalid user"}

    log = {
        "user_id": user_id,
        "garbage_type": data["type"],
        "weight": data["weight"],
        "status": "pending",
        "payment_status": "unpaid",
        "timestamp": datetime.now()
    }

    db.logs.insert_one(log)

    return {"message": "Scan recorded"}

@router.get("/fetch/{reading_id}")
def fetch_iot_reading(reading_id: str):
    reading = db.iot_readings.find_one({"reading_id": reading_id})
    
    if not reading:
        return {"error": "Reading not found"}
        
    if reading.get("is_claimed"):
        return {"error": "This item has already been scanned"}
        
    return {
        "reading_id": reading["reading_id"],
        "name": reading["type"].capitalize(),
        "weight": reading["weight"],
        "points": reading.get("points", 0),
        "bin_id": reading.get("bin_id", "SB-MAIN-01")
    }