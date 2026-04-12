import random, time, requests
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import db
import uuid

import firebase_admin
from firebase_admin import credentials, auth

router = APIRouter()

# 🔥 Firebase init (ek hi baar)
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

router = APIRouter()

# In-memory OTP store
_otp_store: dict = {}  # { phone: { otp, expires_at } }

# ══════════════════════════════════════════════════════════════
#  AUTH — FIREBASE OTP
# ══════════════════════════════════════════════════════════════

# ❌ send-otp REMOVE (Firebase karega)

# POST /verify-otp
@router.post("/verify-otp")
def verify_otp(data: dict):
    try:
        id_token = data.get("otp")  # 🔥 अब OTP nahi, Firebase token hai

        decoded = auth.verify_id_token(id_token)
        phone = decoded.get("phone_number")  # +91XXXXXXXXXX

        if not phone:
            raise HTTPException(status_code=400, detail="Phone not found in token")

        # 🔥 same format me store (without +91)
        phone_clean = phone

        user = db.users.find_one({"phone": phone_clean})
        is_new = user is None

        if is_new:
            return {
                "verified": True,
                "is_new_user": True,
                "token": None,
                "user": None
            }

        return {
            "verified": True,
            "is_new_user": False,
            "token": user["user_id"],
            "user_id": user["user_id"],
            "user": {
                "name": user.get("name", ""),
                "phone": phone_clean,
                "upi": user.get("upi", ""),
                "total_reward": user.get("total_reward", 0),
            }
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Firebase token")



# POST /check-user
@router.post("/check-user")
def check_user(data: dict):
    phone = data.get("phone", "").strip()
    if phone.startswith("+91"):
        phone = phone[3:]
    user = db.users.find_one({"phone": phone})
    if not user:
        return {"is_new_user": True, "token": None, "user": None}
    return {
        "is_new_user": False,
        "token":   user["user_id"],
        "user_id": user["user_id"],
        "user": {
            "name":         user.get("name", ""),
            "phone":        phone,
            "upi":          user.get("upi", ""),
            "total_reward": user.get("total_reward", 0),
        }
    }


# POST /register
@router.post("/register")
def register_user(data: dict):
    phone = data.get("phone", "").strip()
    name  = data.get("name",  "").strip()
    upi   = data.get("upi",   "").strip()

    if phone.startswith("+91"):
        phone = phone[3:]

    if not phone or not name or not upi:
        raise HTTPException(status_code=400, detail="All fields required")

    existing = db.users.find_one({"phone": phone})
    if existing:
        return {
            "token":   existing["user_id"],
            "user_id": existing["user_id"],
            "user": {
                "name":         existing.get("name", ""),
                "phone":        phone,
                "upi":          existing.get("upi", ""),
                "total_reward": existing.get("total_reward", 0),
            }
        }

    user_id = str(uuid.uuid4())
    db.users.insert_one({
        "user_id":      user_id,
        "phone":        phone,
        "name":         name,
        "upi":          upi,
        "total_reward": 0,
        "is_active":    True,
        "created_at":   datetime.now(),
    })

    return {
        "token":   user_id,
        "user_id": user_id,
        "user": {
            "name": name, "phone": phone,
            "upi": upi, "total_reward": 0,
        }
    }


# GET /profile/{user_id}
@router.get("/profile/{user_id}")
def get_profile(user_id: str):
    user = db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# POST /update-profile
@router.post("/update-profile")
def update_profile(data: dict):
    user_id = data.get("user_id")
    update_data = {}
    if "name" in data: update_data["name"] = data["name"]
    if "upi"  in data: update_data["upi"]  = data["upi"]
    db.users.update_one({"user_id": user_id}, {"$set": update_data})
    return {"message": "Profile updated"}


# POST /add-upi
@router.post("/add-upi")
def add_upi(data: dict):
    db.users.update_one(
        {"user_id": data["user_id"]},
        {"$set": {"upi": data["upi"]}}
    )
    return {"message": "UPI added"}


# POST /scan-qr
@router.post("/scan-qr")
def user_deposit_scan(data: dict):
    user_id = data.get("user_id")
    bin_id  = data.get("bin_id")
    if not user_id or not bin_id:
        raise HTTPException(status_code=400, detail="Missing user_id or bin_id")
    bin_doc     = db.bins.find_one({"bin_id": bin_id})
    bin_address = bin_doc.get("address", "") if bin_doc else ""
    new_log = {
        "user_id":        user_id,
        "bin_id":         bin_id,
        "bin_address":    bin_address,
        "garbage_type":   data.get("waste_type", ""),
        "weight":         data.get("weight", 0),
        "image_url":      data.get("image_url", ""),
        "status":         "pending",
        "payment_status": "unpaid",
        "reward":         0,
        "timestamp":      datetime.now(),
    }
    result = db.logs.insert_one(new_log)
    return {"message": "Deposit recorded successfully", "log_id": str(result.inserted_id)}


# GET /my-deposits/{user_id}
@router.get("/my-deposits/{user_id}")
def get_my_deposits(user_id: str):
    logs = list(db.logs.find({"user_id": user_id}).sort("timestamp", -1))
    return [{
        "log_id":         str(log["_id"]),
        "type":           log.get("garbage_type", ""),
        "weight":         log.get("weight", 0),
        "status":         log.get("status", "pending"),
        "payment_status": log.get("payment_status", "unpaid"),
        "timestamp":      str(log.get("timestamp", "")),
        "reward":         log.get("reward", 0),
        "bin_address":    log.get("bin_address", ""),
        "image_url":      log.get("image_url", ""),
        "txn_ref":        log.get("txn_ref", None),
    } for log in logs]


# GET /earnings/{user_id}
@router.get("/earnings/{user_id}")
def get_earnings(user_id: str):
    logs  = list(db.logs.find({"user_id": user_id, "payment_status": "paid"}))
    total = sum(log.get("reward", 0) for log in logs)
    count = len(logs)
    return {
        "total_earnings": total,
        "total_deposits": count,
        "avg_reward":     total / count if count > 0 else 0,
    }


# GET /bins
@router.get("/bins")
def get_all_bins():
    bins = list(db.bins.find())
    return [{
        "id": str(b["_id"]), "bin_id": b.get("bin_id"),
        "name": b.get("address", "SmartBin"), "address": b.get("address"),
        "latitude": b.get("latitude"), "longitude": b.get("longitude"),
        "fill_level": b.get("fill_level", 0), "is_active": b.get("is_active", True),
        "total_deposits": b.get("total_deposits", 0),
    } for b in bins]


# POST /nearby-bins
@router.post("/nearby-bins")
def get_nearby_bins(data: dict):
    bins = list(db.bins.find())
    return [{
        "id": str(b.get("_id")), "bin_id": b.get("bin_id"),
        "name": b.get("address", "SmartBin"), "address": b.get("address"),
        "latitude": b.get("latitude"), "longitude": b.get("longitude"),
        "fill_level": b.get("fill_level", 0), "is_active": b.get("is_active", True),
        "total_deposits": b.get("total_deposits", 0), "distance": 0,
    } for b in bins]