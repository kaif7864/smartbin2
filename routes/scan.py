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