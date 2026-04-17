import os, requests

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
# Note: Twilio Verify Service SID hum sirf OTP ke liye use karte hain. 
# Normal SMS ke liye Twilio ka "Messaging Service SID" ya phone number lagta hai.
# Magar hum Twilio Verify se hi status notifications bhi bhej sakte hain agar 
# humne custom notifications enable ki hon, ya fir plain SMS API use karenge.

def send_sms_notification(to_phone: str, message: str):
    """Sends a standard SMS notification using Twilio REST API"""
    if not TWILIO_SID or not TWILIO_TOKEN:
        print("Twilio credentials missing!")
        return False
    
    # Format phone
    if not to_phone.startswith("+"):
        to_phone = f"+91{to_phone}" if len(to_phone) == 10 else f"+{to_phone}"

    # We can use Twilio Messages API
    # Note: Requires a Twilio Phone Number or Alphanumeric Sender ID
    # For now, let's try the simple messages endpoint.
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
    
    # We'll use the TWILIO_FROM_NUMBER from env
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    if not from_number:
        # Fallback to alphanumeric but warn it might fail in India on trial
        from_number = "SmartId" 

    data = {
        "To": to_phone,
        "From": from_number,
        "Body": message
    }
    
    # If using trial, we might need to use a Twilio purchased number.
    # I will assume the user has a Messaging setup or I'll use simple print logs if it fails.
    
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
