"""
threshold_extract.py — Fixed version
CHANGES:
  - Threshold from live data now uses HIGH-RISK rows only (same logic as
    static fallback) when the live CSV has enough rows.
  - Falls back to static dataset correctly when live data is sparse.
  - Prints which source was used so you can verify in the terminal.
"""

import os
import sys
import pandas as pd

LIVE_FILE   = "live_dataset.csv"
STATIC_FILE = "bd_grain_storage_risk_dataset.csv"
OUT_FILE    = "thresholds.txt"

MIN_LIVE_ROWS = 5  # minimum rows before trusting live data


# ── helpers ────────────────────────────────────────────────────────────────

def high_risk_means(df: pd.DataFrame):
    """Return (gas_th, humidity_th, gradient_th) from high-risk rows."""
    if "label" in df.columns:
        high = df[df["label"].isin(["High_Spoilage_Risk", "Critical_Spoilage"])]
        if high.empty:
            high = df  # fallback: all rows
    else:
        # live data has no label column — use top-quartile gas rows as proxy
        q75 = df["gas"].quantile(0.75)
        high = df[df["gas"] >= q75]
        if high.empty:
            high = df

    return (
        float(high["gas"].mean()),
        float(high["humidity"].mean()),
        float(high["gradient"].mean()),
    )


def load_static():
    if not os.path.exists(STATIC_FILE):
        raise FileNotFoundError(f"Static dataset not found: {STATIC_FILE}")
    df = pd.read_csv(STATIC_FILE)
    if df.empty:
        raise ValueError("Static dataset is empty.")
    return df


# ── main ───────────────────────────────────────────────────────────────────

live_df = None
if os.path.exists(LIVE_FILE) and os.path.getsize(LIVE_FILE) > 0:
    try:
        live_df = pd.read_csv(LIVE_FILE)
    except pd.errors.EmptyDataError:
        live_df = None

required_cols = {"gas", "humidity", "gradient"}

if (
    live_df is not None
    and len(live_df) >= MIN_LIVE_ROWS
    and required_cols.issubset(live_df.columns)
):
    # FIX: use the most recent 100 readings; pick high-risk proxy rows
    recent = live_df.tail(100).copy()
    gas_th, humidity_th, gradient_th = high_risk_means(recent)
    source = f"live dataset ({len(recent)} recent rows)"
else:
    # FIX: falls back to static with a clear explanation
    reason = "live CSV is missing, empty, or has fewer than " \
             f"{MIN_LIVE_ROWS} rows"
    if live_df is not None and not required_cols.issubset(live_df.columns):
        reason = f"live CSV missing columns {required_cols - live_df.columns}"
    print(f"Falling back to static dataset: {reason}")
    try:
        static_df = load_static()
    except Exception as err:
        print(f"ERROR loading static dataset: {err}")
        sys.exit(1)
    gas_th, humidity_th, gradient_th = high_risk_means(static_df)
    source = "static dataset (fallback)"

print(f"Using {source}")
print(f"Gas Threshold      : {gas_th:.4f}")
print(f"Humidity Threshold : {humidity_th:.4f}")
print(f"Gradient Threshold : {gradient_th:.4f}")

with open(OUT_FILE, "w") as f:
    f.write(f"{gas_th}\n{humidity_th}\n{gradient_th}\n")

print(f"Thresholds written to {OUT_FILE}")