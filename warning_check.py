import os
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

THRESHOLD_FILE = "thresholds.txt"
LIVE_FILE = "live_dataset.csv"
BLYNK_TOKEN = os.getenv("BLYNK_TOKEN", "").strip()


def load_thresholds():
    if not os.path.exists(THRESHOLD_FILE):
        raise FileNotFoundError(f"Threshold file not found: {THRESHOLD_FILE}")

    with open(THRESHOLD_FILE, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    if len(lines) < 3:
        raise ValueError("thresholds.txt must contain at least three values")

    return {
        "gas": float(lines[0]),
        "humidity": float(lines[1]),
        "gradient": float(lines[2]),
    }


def load_latest_live():
    if not os.path.exists(LIVE_FILE) or os.path.getsize(LIVE_FILE) == 0:
        return None
    df = pd.read_csv(LIVE_FILE)
    if df.empty:
        return None
    return df.tail(1).iloc[0]


def send_blynk_notify(body: str):
    if not BLYNK_TOKEN:
        return
    # This works on ALL plans — writes directly to label widget
    requests.get(
        "https://blynk.cloud/external/api/update",
        params={"token": BLYNK_TOKEN, "V31": body},
        timeout=10
    )
    # Push notification — PRO plan only, fails silently on free
    try:
        requests.get(
            "https://blynk.cloud/external/api/notify",
            params={"token": BLYNK_TOKEN, "body": body},
            timeout=10
        )
    except Exception:
        pass


def send_sms(body: str):
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("TWILIO_TO_NUMBER")

    if not all([sid, token, from_number, to_number]):
        print("Twilio SMS not sent: missing Twilio environment variables.")
        return

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    payload = {
        "From": from_number,
        "To": to_number,
        "Body": body,
    }
    response = requests.post(url, data=payload, auth=(sid, token), timeout=10)
    print(f"SMS send status: {response.status_code}")
    if response.ok:
        print("SMS sent successfully")
    else:
        print("SMS send failed:", response.text)


def notify_alert(body: str):
    if BLYNK_TOKEN:
        send_blynk_notify(body)
    else:
        print("Blynk notify skipped: missing token")

    send_sms(body)


if __name__ == "__main__":
    try:
        thresholds = load_thresholds()
    except Exception as err:
        print("Unable to load thresholds:", err)
        raise

    latest = load_latest_live()
    if latest is None:
        print("No live data available for warning checks.")
        raise SystemExit(0)

    alerts = []
    if latest["gas"] > thresholds["gas"]:
        alerts.append(f"Gas {latest['gas']} exceeds threshold {thresholds['gas']}")
    if latest["humidity"] > thresholds["humidity"]:
        alerts.append(f"Humidity {latest['humidity']} exceeds threshold {thresholds['humidity']}")
    if latest["gradient"] > thresholds["gradient"]:
        alerts.append(f"Gradient {latest['gradient']} exceeds threshold {thresholds['gradient']}")

    if alerts:
        body = "WARNING: " + "; ".join(alerts)
        print(body)
        notify_alert(body)
    else:
        print("No threshold warnings.")
