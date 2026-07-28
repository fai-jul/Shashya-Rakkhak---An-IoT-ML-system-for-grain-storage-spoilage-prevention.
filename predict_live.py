"""
predict_live.py — Fixed version
CHANGES:
  - Uses all 9 features the model was trained on (added spatial_score, gas_accel).
  - Guards against empty live_dataset.csv.
  - Prints confidence probabilities alongside the class label.
"""

import sys
import pandas as pd
import joblib

MODEL_FILE = "grain_model.pkl"
LIVE_FILE  = "live_dataset.csv"

# FIX: must match train_model.py feature list exactly
FEATURES = [
    "temp",
    "humidity",
    "gas",
    "gradient",
    "gas_trend",
    "humidity_trend",
    "confidence",
    "spatial_score",   # <-- was missing; caused crash on every prediction
    "gas_accel",       # <-- was missing
]

try:
    model = joblib.load(MODEL_FILE)
except FileNotFoundError:
    print(f"ERROR: model file '{MODEL_FILE}' not found. Run train_model.py first.")
    sys.exit(1)

try:
    df = pd.read_csv(LIVE_FILE)
except FileNotFoundError:
    print(f"ERROR: '{LIVE_FILE}' not found.")
    sys.exit(1)

# FIX: guard against empty CSV (logger not running yet)
if df.empty:
    print("No live data yet. Start logger.py and wait for sensor readings.")
    sys.exit(0)

missing = [f for f in FEATURES if f not in df.columns]
if missing:
    print(f"ERROR: live_dataset.csv is missing columns: {missing}")
    print("Make sure you are using the FIXED logger.py which computes spatial_score and gas_accel.")
    sys.exit(1)

latest = df.tail(1)
X = latest[FEATURES]

prediction   = model.predict(X)[0]
probabilities = dict(zip(model.classes_, model.predict_proba(X)[0]))

print(f"LIVE PREDICTION : {prediction}")
print("CONFIDENCE      :")
for label, prob in sorted(probabilities.items(), key=lambda x: -x[1]):
    bar = "█" * int(prob * 20)
    print(f"  {label:<25} {prob*100:5.1f}%  {bar}")