import os
from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from database import db
from bson import ObjectId

router = APIRouter()

# ══════════════════════════════════════════════════════════════
#  ADMIN AUTH
# ══════════════════════════════════════════════════════════════

# POST /admin/login
# body: { email, password }
# Admin credentials are stored in db.admins collection
# To seed first admin, run this in MongoDB:
#   db.admins.insertOne({
#     "email": "admin@smartbin.com",
#     "password": "admin123",
#     "name": "Admin",
#     "admin_id": "admin_001"
#   })
@router.get("/logs")
def get_logs():
    logs = list(db.logs.find())
    result = []
    for log in logs:
        user = db.users.find_one({"user_id": log["user_id"]})
        result.append({
            "log_id": str(log["_id"]),
            "user_id": log["user_id"],
            "upi": user.get("upi", "Not set") if user else "Not set",
            "type": log.get("garbage_type", ""),
            "weight": log.get("weight", 0),
            "status": log.get("status", "pending"),
            "payment_status": log.get("payment_status", "unpaid")
        })
    return result

@router.post("/login")
def admin_login(data: dict):
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    admin = db.admins.find_one({"email": email})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if admin["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return {
        "message":      "Admin login successful",
        "admin_id":     admin["admin_id"],
        "name":         admin.get("name", "Admin"),
        "access_token": admin["admin_id"], # use JWT in production
    }

# ══════════════════════════════════════════════════════════════
#  DASHBOARD STATS
# ══════════════════════════════════════════════════════════════

@router.get("/dashboard/stats")
def get_dashboard_stats():
    total_users    = db.users.count_documents({})
    total_bins     = db.bins.count_documents({})
    total_deposits = db.logs.count_documents({})
    pending_deps   = db.logs.count_documents({"status": "pending"})
    all_txs    = list(db.transactions.find({"status": "success"}))
    total_paid = sum(tx.get("amount", 0) for tx in all_txs)
    pending_logs   = list(db.logs.find({"status": "approved", "payment_status": "unpaid"}))
    pending_amount = sum(log.get("reward", 0) for log in pending_logs)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_logs  = list(db.logs.find({"timestamp": {"$gte": today_start}}))
    today_count = len(today_logs)
    today_rwds  = sum(log.get("reward", 0) for log in today_logs)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly    = []
    for i in range(6, -1, -1):
        day      = datetime.now() - timedelta(days=i)
        day_s    = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_e    = day.replace(hour=23, minute=59, second=59)
        count    = db.logs.count_documents({"timestamp": {"$gte": day_s, "$lte": day_e}})
        weekly.append({
            "day":   day_names[day.weekday()],
            "count": count,
            "date":  day.strftime("%d/%m"),
        })
    return {
        "total_users":           total_users,
        "total_bins":            total_bins,
        "total_deposits":        total_deposits,
        "pending_deposits":      pending_deps,
        "total_rewards_paid":    total_paid,
        "pending_reward_amount": pending_amount,
        "today_deposits":        today_count,
        "today_rewards":         today_rwds,
        "weekly_chart":          weekly,
    }

# ══════════════════════════════════════════════════════════════
#  DEPOSITS / SUBMISSIONS
# ══════════════════════════════════════════════════════════════

@router.post("/approve")
def approve(data: dict):
    log_id = data["log_id"]
    reward = data["reward"]
    log = db.logs.find_one({"_id": ObjectId(log_id)})
    if not log:
        raise HTTPException(status_code=404, detail="Not found")
    db.logs.update_one(
        {"_id": ObjectId(log_id)},
        {"$set": {
            "status": "approved",
            "payment_status": "unpaid",
            "reward": reward
        }}
    )
    return {"message": "Approved successfully"}

@router.get("/deposits")
def get_deposits(status: str = None, page: int = 1, limit: int = 20):
    query = {}
    if status:
        if status == "paid": query["payment_status"] = "paid"
        elif status == "approved": query = {"status": "approved", "payment_status": "unpaid"}
        elif status == "rejected": query["status"] = "rejected"
        else: query = {"status": "pending", "payment_status": {"$ne": "paid"}}
    skip  = (page - 1) * limit
    total = db.logs.count_documents(query)
    logs  = list(db.logs.find(query).sort("timestamp", -1).skip(skip).limit(limit))
    items = []
    for log in logs:
        user = db.users.find_one({"user_id": log["user_id"]}) or {}
        st  = log.get("status", "pending")
        pst = log.get("payment_status", "unpaid")
        if pst == "paid": dep_status = "paid"
        elif st == "approved": dep_status = "approved"
        elif st == "rejected": dep_status = "rejected"
        else: dep_status = "pending"
        image_url = log.get("image_url", "")
        if not image_url and log.get("reading_id"):
            iot_info = db.iot_readings.find_one({"reading_id": log["reading_id"]})
            if iot_info:
                path = iot_info.get("image", "")
                if path and not path.startswith("http"):
                    server_ip = os.environ.get("SERVER_IP", "172.16.42.171")
                    image_url = f"http://{server_ip}:8000/{path}"
                else: image_url = path
        items.append({
            "_id":          str(log["_id"]),
            "user_id":      log["user_id"],
            "user_name":    user.get("name", "Unknown"),
            "user_phone":   user.get("phone", ""),
            "upi_id":       user.get("upi", "Not set"),
            "bin_id":       log.get("bin_id", ""),
            "bin_address":  log.get("bin_address", log.get("type", "")),
            "image_url":    image_url,
            "reading_id":   log.get("reading_id"),
            "weight":       log.get("weight", 0),
            "latitude":     log.get("lat", 0),
            "longitude":    log.get("lng", 0),
            "reward_amount":log.get("reward", 0),
            "status":       dep_status,
            "created_at":   str(log.get("timestamp", "")),
            "txn_ref":      log.get("txn_ref", None),
        })
    return {"items": items, "total": total, "page": page}

@router.get("/deposits/{deposit_id}")
def get_deposit(deposit_id: str):
    log  = db.logs.find_one({"_id": ObjectId(deposit_id)})
    if not log: raise HTTPException(status_code=404, detail="Deposit not found")
    user = db.users.find_one({"user_id": log["user_id"]}) or {}
    st  = log.get("status", "pending")
    pst = log.get("payment_status", "unpaid")
    if pst == "paid": dep_status = "paid"
    elif st == "approved": dep_status = "approved"
    elif st == "rejected": dep_status = "rejected"
    else: dep_status = "pending"
    return {
        "_id":          str(log["_id"]),
        "user_id":      log["user_id"],
        "user_name":    user.get("name", "Unknown"),
        "user_phone":   user.get("phone", ""),
        "upi_id":       user.get("upi", "Not set"),
        "bin_id":       log.get("bin_id", ""),
        "bin_address":  log.get("bin_address", log.get("type", "")),
        "image_url":    log.get("image_url", ""),
        "latitude":     log.get("lat", 0),
        "longitude":    log.get("lng", 0),
        "reward_amount":log.get("reward", 0),
        "status":       dep_status,
        "created_at":   str(log.get("timestamp", "")),
        "txn_ref":      log.get("txn_ref", None),
    }

@router.patch("/deposits/{deposit_id}/approve")
def approve_deposit(deposit_id: str):
    db.logs.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "approved", "payment_status": "unpaid"}})
    return {"message": "Deposit approved"}

@router.patch("/deposits/{deposit_id}/reject")
def reject_deposit(deposit_id: str, data: dict = {}):
    reason = data.get("reason", "")
    db.logs.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "rejected", "rejection_reason": reason}})
    log = db.logs.find_one({"_id": ObjectId(deposit_id)})
    user = db.users.find_one({"user_id": log["user_id"]})
    if user and user.get("phone"):
        from utils import send_sms_notification
        msg = f"Hi {user.get('name', 'User')}, your SmartBin deposit was rejected. Reason: {reason or 'Verification failed'}."
        send_sms_notification(user["phone"], msg)
    return {"message": "Deposit rejected"}

# ══════════════════════════════════════════════════════════════
#  PAYMENTS
# ══════════════════════════════════════════════════════════════

@router.get("/payments/pending")
def get_pending_payments():
    logs = list(db.logs.find({"status": "approved", "payment_status": "unpaid"}))
    items = []
    for log in logs:
        user = db.users.find_one({"user_id": log["user_id"]}) or {}
        items.append({
            "_id":          str(log["_id"]),
            "user_id":      log["user_id"],
            "user_name":    user.get("name", "Unknown"),
            "user_phone":   user.get("phone", ""),
            "upi_id":       user.get("upi", "Not set"),
            "reward_amount":log.get("reward", 0),
            "bin_address":  log.get("bin_address", ""),
            "created_at":   str(log.get("timestamp", "")),
        })
    return items

@router.post("/payments/send")
def send_payment(data: dict):
    deposit_id = data["deposit_id"]
    amount     = data["amount"]
    upi_id     = data["upi_id"]
    log = db.logs.find_one({"_id": ObjectId(deposit_id)})
    if not log: raise HTTPException(status_code=404, detail="Deposit not found")
    import uuid
    txn_ref = f"SB_{uuid.uuid4().hex[:10].upper()}"
    db.logs.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "approved", "payment_status": "paid", "txn_ref": txn_ref}})
    db.transactions.insert_one({
        "transaction_id": txn_ref,
        "user_id": log["user_id"],
        "deposit_id": deposit_id,
        "amount": amount,
        "upi_id": upi_id,
        "type": "payout",
        "timestamp": datetime.now(),
        "status": "success"
    })
    db.users.update_one({"user_id": log["user_id"]}, {"$inc": {"total_reward": amount}})
    user = db.users.find_one({"user_id": log["user_id"]})
    if user and user.get("phone"):
        from utils import send_sms_notification
        msg = f"Hi {user.get('name', 'User')}, your reward of ₹{amount} has been sent! Ref: {txn_ref}"
        send_sms_notification(user["phone"], msg)
    return {"message": "Payment marked as sent", "txn_ref": txn_ref, "upi_id":  upi_id, "amount":  amount}

# ══════════════════════════════════════════════════════════════
#  BINS
# ══════════════════════════════════════════════════════════════

@router.get("/bins")
def get_bins():
    bins = list(db.bins.find())
    return [{
        "_id":           str(b["_id"]),
        "address":       b.get("address", b.get("name", "")),
        "latitude":      b.get("latitude", b.get("lat", 0)),
        "longitude":     b.get("longitude", b.get("lng", 0)),
        "fill_level":    b.get("fill_level", 0),
        "is_active":     b.get("is_active", True),
        "total_deposits":b.get("total_deposits", 0),
        "installed_at":  str(b.get("installed_at", "")),
    } for b in bins]

@router.post("/bins")
def add_bin(data: dict):
    import uuid
    bin_doc = {
        "bin_id":       str(uuid.uuid4()),
        "address":      data["address"],
        "latitude":     data["latitude"],
        "longitude":    data["longitude"],
        "is_active":    data.get("is_active", True),
        "fill_level":   0,
        "total_deposits": 0,
        "installed_at": datetime.now(),
    }
    result = db.bins.insert_one(bin_doc)
    bin_doc["_id"] = str(result.inserted_id)
    return bin_doc

@router.patch("/bins/{bin_id}")
def update_bin(bin_id: str, data: dict):
    db.bins.update_one({"_id": ObjectId(bin_id)}, {"$set": data})
    return {"message": "Updated"}

@router.delete("/bins/{bin_id}")
def delete_bin(bin_id: str):
    db.bins.delete_one({"_id": ObjectId(bin_id)})
    return {"message": "Deleted"}

# ══════════════════════════════════════════════════════════════
#  USERS
# ══════════════════════════════════════════════════════════════

@router.post("/users/{user_id}/status")
def update_user_status(user_id: str, data: dict):
    status = data.get("status", "active")
    db.users.update_one({"user_id": user_id}, {"$set": {"status": status}})
    db.notifications.insert_one({
        "title": "Account Alert",
        "message": f"Your account status has been updated to {status}.",
        "recipient_id": user_id,
        "timestamp": datetime.now()
    })
    return {"message": f"User status updated to {status}"}

@router.get("/users")
def get_users(search: str = None, page: int = 1, limit: int = 20):
    query = {}
    if search: query = {"$or": [{"name": {"$regex": search, "$options": "i"}}, {"phone": {"$regex": search, "$options": "i"}}]}
    skip  = (page - 1) * limit
    total = db.users.count_documents(query)
    users = list(db.users.find(query).skip(skip).limit(limit))
    items = []
    for u in users:
        total_deps   = db.logs.count_documents({"user_id": u["user_id"]})
        pending_deps = db.logs.count_documents({"user_id": u["user_id"], "status": "pending"})
        items.append({
            "_id":             u["user_id"],
            "name":            u.get("name", ""),
            "phone":           u.get("phone", ""),
            "upi_id":          u.get("upi", ""),
            "total_earnings":  u.get("total_reward", 0),
            "total_deposits":  total_deps,
            "pending_deposits":pending_deps,
            "joined_at":       str(u.get("created_at", "")),
            "avatar":          u.get("avatar", "🌿"),
            "status":          u.get("status", "active"),
            "is_active":       u.get("is_active", True),
        })
    return {"items": items, "total": total}

@router.patch("/users/{user_id}/status")
def toggle_user_status(user_id: str, data: dict):
    db.users.update_one({"user_id": user_id}, {"$set": {"is_active": data["is_active"]}})
    return {"message": "Status updated"}

# ══════════════════════════════════════════════════════════════
#  UPI VPA VERIFY
# ══════════════════════════════════════════════════════════════

@router.get("/verify-upi")
def verify_upi(upi_id: str):
    import requests
    try:
        res = requests.get(f"https://upivalidator.samsiddha.com/validate?upi={upi_id}", timeout=5)
        data = res.json()
        if data.get("status") == "SUCCESS":
            return {"valid": True, "name": data.get("name", "Unknown"), "upi_id": upi_id}
        else: return {"valid": False, "name": None, "upi_id": upi_id}
    except Exception:
        user = db.users.find_one({"upi": upi_id})
        if user: return {"valid": True, "name": user.get("name", "Unknown"), "upi_id": upi_id}
        return {"valid": False, "name": None, "upi_id": upi_id}

@router.get("/transactions")
def get_transactions(limit: int = 100):
    txs = list(db.transactions.find().sort("timestamp", -1).limit(limit))
    items = []
    for tx in txs:
        user = db.users.find_one({"user_id": tx["user_id"]}) or {}
        items.append({
            "_id":           str(tx["_id"]),
            "txn_id":        tx["transaction_id"],
            "user_name":     user.get("name", "Unknown"),
            "amount":        tx["amount"],
            "upi_id":        tx["upi_id"],
            "timestamp":     str(tx["timestamp"]),
            "type":          tx["type"],
        })
    return items

@router.get("/settings")
def get_admin_settings():
    settings = db.settings.find_one({"id": "global"})
    if not settings:
        settings = {"id": "global", "broadcast_message": "Welcome to SmartBin! Start recycling today.", "rates": {"plastic": 0.05, "liquid": 0.10, "glass": 0.08, "metal": 0.15}}
        db.settings.insert_one(settings)
    settings["_id"] = str(settings["_id"])
    return settings

@router.post("/settings")
def update_admin_settings(data: dict):
    db.settings.update_one({"id": "global"}, {"$set": data}, upsert=True)
    if "broadcast_message" in data:
         db.notifications.insert_one({"title": "System Announcement", "message": data["broadcast_message"], "recipient_id": "all", "timestamp": datetime.now()})
    return {"message": "Settings updated successfully"}

@router.get("/ai-insights")
def get_ai_insights():
    bins = list(db.bins.find().sort("fill_level", -1))
    bin_alert = "All systems operational."
    if bins and bins[0].get("fill_level", 0) > 80: bin_alert = f"Urgent: Bin at {bins[0].get('address')} is {bins[0]['fill_level']}% full. Schedule cleaning."
    elif bins and bins[0].get("fill_level", 0) > 50: bin_alert = f"Maintenance Tip: {bins[0].get('address')} is filling up fast."
    now = datetime.now()
    last_week = now - timedelta(days=7)
    recent_logs = list(db.logs.find({"timestamp": {"$gte": last_week}}))
    growth = "Recycling activity is stable."
    if len(recent_logs) > 50: growth = "Collection has increased by 15% this week! Great community engagement."
    elif len(recent_logs) < 10: growth = "Recycling is slow this week. Consider sending a system broadcast."
    return {"bin_alert": bin_alert, "trend_insight": growth, "efficiency_score": "94%", "active_users_today": db.logs.distinct("user_id", {"timestamp": {"$gte": now.replace(hour=0, minute=0, second=0)}}).__len__()}

@router.get("/notifications")
def get_user_notifications(user_id: str):
    notes = list(db.notifications.find({"$or": [{"recipient_id": user_id}, {"recipient_id": "all"}]}).sort("timestamp", -1).limit(50))
    for note in notes:
        note["_id"] = str(note["_id"])
        note["timestamp"] = str(note["timestamp"])
    return notes
