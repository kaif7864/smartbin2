from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# ══════════════════════════════════════════════════════════════
#  USER BUNDLE DATA
# ══════════════════════════════════════════════════════════════

class UserBadge(BaseModel):
    name: str
    icon: str
    desc: str

class UserProfile(BaseModel):
    user_id: str
    phone: str
    name: str
    upi: Optional[str] = ""
    avatar: Optional[str] = "🌊"
    total_reward: float = 0.0
    is_active: bool = True
    badges: List[UserBadge] = []
    created_at: datetime = Field(default_factory=datetime.now)

# ══════════════════════════════════════════════════════════════
#  ADMIN DATA
# ══════════════════════════════════════════════════════════════

class AdminProfile(BaseModel):
    admin_id: str
    email: str
    password: str # In prod, store hash
    name: str
    role: str = "admin"

# ══════════════════════════════════════════════════════════════
#  BIN / IOT DATA
# ══════════════════════════════════════════════════════════════

class SmartBin(BaseModel):
    bin_id: str
    address: str
    latitude: float
    longitude: float
    fill_level: int = 0
    is_active: bool = True
    total_deposits: int = 0
    last_ping: datetime = Field(default_factory=datetime.now)

# ══════════════════════════════════════════════════════════════
#  LOGS / DEPOSITS
# ══════════════════════════════════════════════════════════════

class DepositLog(BaseModel):
    user_id: str
    bin_id: str
    bin_address: str
    garbage_type: str
    weight: float
    image_url: Optional[str] = ""
    status: str = "pending" # pending, approved, rejected, completed
    payment_status: str = "unpaid" # unpaid, paid
    reward: float = 0.0
    txn_ref: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
