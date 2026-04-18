import random, time, requests, os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import db
import uuid
from jose import jwt, JWTError

router = APIRouter()

# 🔥 Twilio Config
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID")

# ══════════════════════════════════════════════════════════════
#  AUTH — TWILIO VERIFY
# ══════════════════════════════════════════════════════════════

# POST /send-otp
@router.post("/send-otp")
async def send_otp(data: dict):
    phone = data.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number required")
    
    # Format: +91XXXXXXXXXX
    if not phone.startswith("+"):
        phone = f"+91{phone}" if len(phone) == 10 else f"+{phone}"

    url = f"https://verify.twilio.com/v2/Services/{VERIFY_SERVICE_SID}/Verifications"
    resp = requests.post(
        url,
        auth=(TWILIO_SID, TWILIO_TOKEN),
        data={"To": phone, "Channel": "sms"}
    )

    if resp.status_code == 201:
        return {"status": "success", "message": "OTP sent via Twilio"}
    else:
        print(f"Twilio Error: {resp.text}")
        raise HTTPException(status_code=resp.status_code, detail=resp.json())

# POST /verify-otp
@router.post("/verify-otp")
async def verify_otp(data: dict):
    try:
        phone = data.get("phone")
        otp = data.get("otp")
        
        if not phone or not otp:
            raise HTTPException(status_code=400, detail="Phone and OTP required")

        # Format: +91XXXXXXXXXX
        full_phone = phone
        if not full_phone.startswith("+"):
            full_phone = f"+91{full_phone}" if len(full_phone) == 10 else f"+{full_phone}"

        # 1. Twilio Check
        url = f"https://verify.twilio.com/v2/Services/{VERIFY_SERVICE_SID}/VerificationCheck"
        resp = requests.post(
            url,
            auth=(TWILIO_SID, TWILIO_TOKEN),
            data={"To": full_phone, "Code": otp}
        )

        if resp.status_code != 200 or resp.json().get("status") != "approved":
            raise HTTPException(status_code=401, detail="Invalid or expired OTP")

        # 2. Token se Phone number nikalna (Clean)
        phone_clean = phone.replace("+", "")
        if phone_clean.startswith("91") and len(phone_clean) > 10:
            phone_clean = phone_clean[2:]

        # 3. MongoDB me User check karna
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
            "bundle": _get_user_bundle(user["user_id"])
        }

    except HTTPException as h:
        raise h
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_user_bundle(user_id: str):
    """Helper to get full user data in one bundle"""
    user = db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        return None

    # Handle Legacy Users (Missing Referral Code)
    if not user.get("referral_code"):
        name_part = (user.get("name", "USER")).split()[0].upper()
        phone_part = (user.get("phone", "0000"))[-3:]
        ref_code = f"SB-{name_part}-{phone_part}"
        db.users.update_one({"user_id": user_id}, {"$set": {"referral_code": ref_code}})
        user["referral_code"] = ref_code
       
    logs = list(db.logs.find({"user_id": user_id}))
    
    # 1. Earnings
    settled = sum(log.get("reward", 0) for log in logs if log.get("payment_status") == "paid")
    pending = sum(log.get("reward", 0) for log in logs if log.get("status") == "approved" and log.get("payment_status") == "unpaid")
    lifetime = user.get("total_reward", 0)
    
    # 2. Impact
    total_weight = sum(float(str(log.get("weight", 0)).replace("g", "").strip() or 0) for log in logs)
    total_weight_kg = total_weight / 1000.0
    co2_saved = total_weight_kg * 0.5 
    bins_visited = len(set(log.get("bin_id") for log in logs if log.get("bin_id")))
    
    # 3. Gamification Level (Tree Growth)
    level_name = "Seed"
    progress = 0
    if lifetime > 500:
        level_name = "Forest Giant"
        progress = 1.0
    elif lifetime > 200:
        level_name = "Tree"
        progress = (lifetime - 200) / 300
    elif lifetime > 50:
        level_name = "Sapling"
        progress = (lifetime - 50) / 150
    else:
        progress = lifetime / 50
    
    # 4. Counts
    pending_req = sum(1 for log in logs if log.get("status") == "pending")
    completed_dep = sum(1 for log in logs if log.get("status") in ["approved", "paid", "completed"])
    
    # 5. Recent Activity (History)
    recent = sorted(logs, key=lambda x: x.get("timestamp") if isinstance(x.get("timestamp"), datetime) else datetime.min, reverse=True)[:20]
    activity = [{
        "log_id": str(log["_id"]),
        "title": log.get("title") or f"{log.get('garbage_type', 'Waste').capitalize()} Deposit",
        "subtitle": log.get("bin_address", "SmartBin"),
        "reward": log.get("reward", 0),
        "status": "paid" if log.get("payment_status") == "paid" else log.get("status", "pending"),
        "timestamp": str(log.get("timestamp", "")),
        "weight": log.get("weight", 0)
    } for log in recent]

    return {
        "profile": {
            "user_id": user_id,
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "phone": user.get("phone", ""),
            "upi": user.get("upi", ""),
            "avatar": user.get("avatar", "🌊"),
            "role": user.get("role", "user"),
            "badges": user.get("badges", []),
            "referral_code": user.get("referral_code", ""),
            "level": {"name": level_name, "progress": round(progress, 2)},
        },
        "stats": {
            "earnings": {
                "lifetime": lifetime,
                "settled": settled,
                "pending": pending
            },
            "impact": {
                "weight_recycled_kg": round(total_weight_kg, 2),
                "co2_saved_kg": round(co2_saved, 2),
                "bins_visited": bins_visited
            },
            "counts": {
                "pending_requests": pending_req,
                "completed_deposits": completed_dep
            }
        },
        "recent_activity": activity
    }



# POST /check-user
@router.post("/check-user")
def check_user(data: dict):
    # Clean phone to 10 digits
    phone = data.get("phone", "").replace("+", "").strip()
    if phone.startswith("91") and len(phone) > 10:
        phone = phone[2:]
    user = db.users.find_one({"phone": phone})
    if not user:
        return {"is_new_user": True, "token": None, "user": None}
    return {
        "is_new_user": False,
        "token":   user["user_id"],
        "user_id": user["user_id"],
        "bundle":  _get_user_bundle(user["user_id"])
    }


# POST /register
@router.post("/register")
def register_user(data: dict):
    # Clean phone to 10 digits
    phone = data.get("phone", "").replace("+", "").strip()
    if phone.startswith("91") and len(phone) > 10:
        phone = phone[2:]
        
    name  = data.get("name",  "").strip()
    upi   = data.get("upi",   "").strip()

    if not phone or not name or not upi:
        raise HTTPException(status_code=400, detail="All fields required")

    existing = db.users.find_one({"phone": phone})
    if existing:
        return {
            "token":   existing["user_id"],
            "user_id": existing["user_id"],
            "user": {
                "name":         existing.get("name", ""),
                "email":        existing.get("email", ""),
                "phone":        phone,
                "upi":          existing.get("upi", ""),
                "total_reward": existing.get("total_reward", 0),
            }
        }

    email = data.get("email", "").strip()
    # Support both key names for flexibility
    ref_code = (data.get("applied_referral") or data.get("referral_code") or "").strip().upper()

    user_id = f"sb{phone[-4:]}"
    if db.users.find_one({"user_id": user_id}):
        user_id = f"sb{phone[-4:]}{random.randint(10, 99)}"

    # Generate Unique Referral Code
    my_ref_code = f"SB-{name.split()[0].upper()}-{phone[-3:]}"
    
    joining_bonus = 0
    if ref_code:
        # Find who owns this code
        referrer = db.users.find_one({"referral_code": ref_code})
        if referrer:
            joining_bonus = 10
            # Reward Referrer
            db.users.update_one({"user_id": referrer["user_id"]}, {"$inc": {"total_reward": 10}})
            db.logs.insert_one({
                "user_id": referrer["user_id"],
                "title": f"Referral Bonus: {name}",
                "reward": 10,
                "status": "approved",
                "payment_status": "unpaid",
                "timestamp": datetime.now()
            })

            # Send SMS to Referrer
            if referrer.get("phone"):
                from utils import send_sms_notification
                ref_msg = f"Good news! {name} joined using your code. You've earned ₹10 referral bonus!"
                send_sms_notification(referrer["phone"], ref_msg)

    db.users.insert_one({
        "user_id":      user_id,
        "phone":        phone,
        "name":         name,
        "email":        email,
        "upi":          upi,
        "avatar":       "🌊",
        "role":         "user", 
        "total_reward": joining_bonus,
        "is_active":    True,
        "badges":       [],
        "referral_code": my_ref_code,
        "referred_by":   ref_code,
        "created_at":    datetime.now(),
    })

    if joining_bonus > 0:
        db.logs.insert_one({
            "user_id": user_id,
            "title": "Welcome Bonus (Referral)",
            "reward": 10,
            "status": "approved",
            "payment_status": "unpaid",
            "timestamp": datetime.now()
        })

    return {
        "token":   user_id,
        "user_id": user_id,
        "bundle":  _get_user_bundle(user_id)
    }

# POST /redeem-request
@router.post("/redeem-request")
def request_redemption(data: dict):
    user_id = data.get("user_id")
    if not user_id: raise HTTPException(status_code=400, detail="User ID required")
    
    user = db.users.find_one({"user_id": user_id})
    if not user: raise HTTPException(status_code=404, detail="User not found")
    
    # 1. Sum up all Approved & Unpaid rewards
    logs = list(db.logs.find({"user_id": user_id, "status": "approved", "payment_status": "unpaid"}))
    total_requested = sum(log.get("reward", 0) for log in logs)
    
    if total_requested < 50:
        raise HTTPException(status_code=400, detail="Minimum ₹50 required to redeem")
        
    # 2. Mark them as "redeem_sent" for admin visibility
    db.logs.update_many(
        {"user_id": user_id, "status": "approved", "payment_status": "unpaid"},
        {"$set": {"redemption_requested_at": datetime.now()}}
    )
    
    return {"message": "Redemption request sent to admin", "amount": total_requested}

# GET /stories
@router.get("/stories")
def get_stories():
    return [
        {"id": "1", "title": "Plastic Waste", "icon": "🧴", "tip": "Did you know? A plastic bottle takes 450 years to decompose."},
        {"id": "2", "title": "CO2 Impact", "icon": "🌍", "tip": "Recycling 1 ton of paper saves 17 trees and prevents CO2 emission."},
        {"id": "3", "title": "Metal Power", "icon": "🥫", "tip": "Aluminum cans save 95% energy when recycled vs new production."},
        {"id": "4", "title": "Planet Hero", "icon": "✨", "tip": "Every item you deposit helps reduce landfill waste. You are a Hero!"},
    ]

@router.post("/update-fcm")
def update_fcm(data: dict):
    user_id = data.get("user_id")
    fcm_token = data.get("fcm_token")
    if not user_id or not fcm_token:
        raise HTTPException(status_code=400, detail="User ID and FCM Token required")
    
    db.users.update_one({"user_id": user_id}, {"$set": {"fcm_token": fcm_token}})
    return {"status": "success", "message": "FCM token updated"}

@router.get("/profile/{user_id}")
def get_profile(user_id: str):
    bundle = _get_user_bundle(user_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="User not found")
    return bundle


@router.post("/update-profile")
def update_profile(data: dict):
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
        
    update_data = {}
    if "name" in data:   update_data["name"]   = data.get("name")
    if "email" in data:  update_data["email"]  = data.get("email")
    if "upi"  in data:    update_data["upi"]    = data.get("upi")
    if "avatar" in data: update_data["avatar"] = data.get("avatar")

    if update_data:
        db.users.update_one({"user_id": user_id}, {"$set": update_data})

    return {
        "status": "success",
        "bundle": _get_user_bundle(user_id)
    }

@router.post("/deposit")
def create_deposit(data: dict):
    user_id = data.get("user_id")
    reward = data.get("reward", 0)
    items = data.get("items", [])

    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")

    # Potential Badges List
    all_badges = [
        {"id": "earth_hero", "name": "Earth Hero", "icon": "🌍", "desc": "First 5 items deposited"},
        {"id": "plastic_warrior", "name": "Plastic Warrior", "icon": "🛡️", "desc": "Recycled 10 bottles"},
        {"id": "clean_pro", "name": "Clean Pro", "icon": "✨", "desc": "Perfect sorting"},
        {"id": "liquid_legend", "name": "Liquid Legend", "icon": "🌊", "desc": "Top 1% recycler"}
    ]

    reading_id = data.get("reading_id")
    log_entry = {
        "user_id": user_id,
        "title": f"Recycled {items[0]['name']}" if items else "Recycled Items",
        "subtitle": f"{datetime.now().strftime('%d %b, %H:%M')}",
        "reward": reward,
        "reading_id": reading_id,
        "weight": str(items[0].get("weight", "0")).replace("g", "") if items else "0",
        "status": "pending",
        "payment_status": "unpaid",
        "items": items,
        "timestamp": datetime.now()
    }
    
    db.logs.insert_one(log_entry)

    if reading_id:
        db.iot_readings.update_one({"reading_id": reading_id}, {"$set": {"is_claimed": True}})

    # Logic to award a new badge randomly (or based on criteria)
    user = db.users.find_one({"user_id": user_id})
    user_badges = user.get("badges", [])
    new_badge = None
    
    # Simple chance to win a badge if they have items
    if len(items) > 0:
        for b in all_badges:
            # If user doesn't have this badge, award it
            if not any(ub.get("id") == b["id"] for ub in user_badges):
                db.users.update_one({"user_id": user_id}, {"$push": {"badges": b}})
                new_badge = b
                break 

    return {
        "status": "success",
        "new_badge": new_badge, # This will trigger scratch card on frontend
        "bundle": _get_user_bundle(user_id)
    }


# POST /add-upi
@router.post("/add-upi")
def add_upi(data: dict):
    db.users.update_one(
        {"user_id": data["user_id"]},
        {"$set": {"upi": data["upi"]}}
    )
    return {"message": "UPI added"}


from database import db, POINTS_MAP
# POST /scan-qr
@router.post("/scan-qr")
def user_deposit_scan(data: dict):
    user_id = data.get("user_id")
    bin_id  = data.get("bin_id")
    if not user_id or not bin_id:
        raise HTTPException(status_code=400, detail="Missing user_id or bin_id")
    
    bin_doc     = db.bins.find_one({"bin_id": bin_id})
    bin_address = bin_doc.get("address", "SmartBin") if bin_doc else "SmartBin"
    
    waste_type = data.get("waste_type", "").lower()
    reward = POINTS_MAP.get(waste_type, 0) # Use points as initial reward
    
    new_log = {
        "user_id":        user_id,
        "bin_id":         bin_id,
        "bin_address":    bin_address,
        "garbage_type":   waste_type,
        "weight":         data.get("weight", 0),
        "image_url":      data.get("image_url", ""),
        "status":         "pending",
        "payment_status": "unpaid",
        "reward":         reward,
        "timestamp":      datetime.now(),
    }
    result = db.logs.insert_one(new_log)
    return {"message": "Deposit recorded successfully", "log_id": str(result.inserted_id), "estimated_reward": reward}



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
    logs = list(db.logs.find({"user_id": user_id}))
    
    # 1. Total (Lifetime) from user profile or summed logs
    user = db.users.find_one({"user_id": user_id})
    lifetime = user.get("total_reward", 0) if user else 0
    
    # 2. Settled (Paid)
    settled = sum(log.get("reward", 0) for log in logs if log.get("payment_status") == "paid")
    
    # 3. Pending (Approved but not paid)
    pending = sum(log.get("reward", 0) for log in logs if log.get("status") == "approved" and log.get("payment_status") == "unpaid")
    
    return {
        "lifetime": lifetime,
        "settled":  settled,
        "pending":  pending
    }


# GET /stats/{user_id}
@router.get("/stats/{user_id}")
def get_user_stats(user_id: str):
    user = db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    logs = list(db.logs.find({"user_id": user_id}))
    
    # Earnings logic
    settled = sum(log.get("reward", 0) for log in logs if log.get("payment_status") == "paid")
    pending = sum(log.get("reward", 0) for log in logs if log.get("status") == "approved" and log.get("payment_status") == "unpaid")
    lifetime = user.get("total_reward", 0)
    
    # Recycling stats
    total_weight = sum(float(str(log.get("weight", 0)).replace("g", "").strip() or 0) for log in logs)
    total_weight_kg = total_weight / 1000.0
    co2_saved = total_weight_kg * 0.5 # 0.5kg CO2 per 1kg recycled
    
    # Count unique bins
    bins_visited = len(set(log.get("bin_id") for log in logs if log.get("bin_id")))
    
    # Request counts
    pending_req = sum(1 for log in logs if log.get("status") == "pending")
    completed_dep = sum(1 for log in logs if log.get("status") in ["approved", "paid", "completed"])
    
    # Recent activity
    recent = sorted(logs, key=lambda x: x.get("timestamp") if isinstance(x.get("timestamp"), datetime) else datetime.min, reverse=True)[:5]
    activity = [{
        "title": f"{log.get('garbage_type', 'Waste').capitalize()} Deposit",
        "subtitle": log.get("bin_address", "SmartBin"),
        "reward": log.get("reward", 0),
        "status": "paid" if log.get("payment_status") == "paid" else log.get("status", "pending"),
        "timestamp": str(log.get("timestamp", "")),
        "weight": log.get("weight", 0)
    } for log in recent]

    return {
        "earnings": {
            "lifetime": lifetime,
            "settled": settled,
            "pending": pending
        },
        "impact": {
            "weight_recycled_kg": round(total_weight_kg, 2),
            "co2_saved_kg": round(co2_saved, 2),
            "bins_visited": bins_visited
        },
        "counts": {
            "pending_requests": pending_req,
            "completed_deposits": completed_dep
        },
        "recent_activity": activity
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


# GET /leaderboard
@router.get("/leaderboard")
def get_leaderboard():
    # Fetch top 10 users by reward
    users = list(db.users.find({}, {"_id": 0, "name": 1, "avatar": 1, "total_reward": 1, "user_id": 1}).sort("total_reward", -1).limit(10))
    
    leaderboard = []
    for index, u in enumerate(users):
        leaderboard.append({
            "rank": index + 1,
            "name": u.get("name", "Smart User"),
            "avatar": u.get("avatar", "🌊"),
            "points": u.get("total_reward", 0),
            "user_id": u.get("user_id")
        })
    
    return leaderboard


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