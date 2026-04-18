import os, requests, json
import firebase_admin
from firebase_admin import credentials, messaging

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# Initialize Firebase Admin SDK
try:
    if not firebase_admin._apps:
        firebase_creds = os.getenv("FIREBASE_CREDENTIALS")
        if firebase_creds:
            cred_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
        else:
            cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
except Exception as e:
    print(f"Firebase Admin Init Error: {e}")

def send_push_notification(fcm_token: str, title: str, body: str):
    """Sends a push notification via Firebase Cloud Messaging"""
    if not fcm_token: return False
    
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=fcm_token,
        )
        response = messaging.send(message)
        print(f"Successfully sent push notification: {response}")
        return True
    except Exception as e:
        print(f"Error sending push notification: {e}")
        return False

def send_sms_notification(to_phone: str, message: str):
    """Sends a standard SMS notification using Twilio REST API"""
    if not TWILIO_SID or not TWILIO_TOKEN:
        print("Twilio credentials missing!")
        return False
    
    if not to_phone.startswith("+"):
        to_phone = f"+91{to_phone}" if len(to_phone) == 10 else f"+{to_phone}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    if not from_number:
        from_number = "SmartId" 

    data = {
        "To": to_phone,
        "From": from_number,
        "Body": message
    }
    
    try:
        resp = requests.post(url, auth=(TWILIO_SID, TWILIO_TOKEN), data=data)
        if resp.status_code == 201:
            print(f"SMS Sent to {to_phone}: {message}")
            return True
        else:
            print(f"SMS Failed: {resp.text}")
            return False
    except Exception as e:
        print(f"SMS Error: {e}")
        return False

def notify_user(user: dict, title: str, message: str):
    """Multi-channel notification (Push first, then SMS)"""
    success = False
    
    # Try Push first (Instant & Free)
    if user.get("fcm_token"):
        success = send_push_notification(user["fcm_token"], title, message)
    
    # Always send SMS if user wants or as backup (optional logic)
    # For now, let's just use SMS if push fails or as secondary
    if not success and user.get("phone"):
        send_sms_notification(user["phone"], message)
    
    return success
