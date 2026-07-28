import os
import requests
from dotenv import load_dotenv

load_dotenv()

BLYNK_TOKEN = os.getenv("BLYNK_TOKEN", "").strip()
THRESHOLD_FILE = "thresholds.txt"

if not BLYNK_TOKEN:
    raise ValueError(
        "Blynk auth token is required. Set the BLYNK_TOKEN environment variable "
        "(see .env.example)."
    )


def load_thresholds():
    if not os.path.exists(THRESHOLD_FILE):
        raise FileNotFoundError(f"Threshold file not found: {THRESHOLD_FILE}")

    with open(THRESHOLD_FILE, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    if len(lines) < 3:
        raise ValueError("Threshold file must contain at least 3 values")

    return [lines[0], lines[1], lines[2]]


gas_th, humidity_th, gradient_th = load_thresholds()

for pin, value in [("V20", gas_th), ("V21", humidity_th), ("V22", gradient_th)]:
    params = {"token": BLYNK_TOKEN, pin: value}
    response = requests.get("https://blynk.cloud/external/api/update", params=params, timeout=10)
    print(f"UPDATE {pin}={value}: {response.status_code}")
    response.raise_for_status()

print("BLYNK UPDATED")