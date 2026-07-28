"""
auto_pipeline.py — Fixed version
CHANGES:
  - Training is only triggered on first run OR when live dataset has grown
    by RETRAIN_EVERY new rows since last train (not every single boot).
  - Pipeline steps run in the correct order.
  - predict_live.py is called after each cycle so you see a live prediction.
  - Graceful error handling: one failed step does not kill the whole loop.
"""

import os
import sys
import time
import subprocess

python_exe   = sys.executable
LIVE_FILE    = "live_dataset.csv"
RETRAIN_EVERY = 50   # retrain model every N new live rows
LOOP_INTERVAL = 60   # seconds between pipeline cycles

last_trained_at_row = 0  # track how many rows existed at last training


def run(script: str) -> int:
    """Run a Python script and return its exit code."""
    print(f"\n>>> {script}")
    result = subprocess.run([python_exe, script])
    print(f"    exit code: {result.returncode}")
    return result.returncode


def live_row_count() -> int:
    """Return number of data rows in live_dataset.csv (0 if missing/empty)."""
    if not os.path.exists(LIVE_FILE) or os.path.getsize(LIVE_FILE) == 0:
        return 0
    try:
        with open(LIVE_FILE, "r") as f:
            # subtract 1 for the header line
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return 0


# ── Initial training ────────────────────────────────────────────────────────
print("=" * 50)
print("INITIAL TRAINING on static dataset")
print("=" * 50)
if run("train_model.py") != 0:
    print("ERROR: initial training failed. Fix train_model.py before continuing.")
    sys.exit(1)

last_trained_at_row = live_row_count()

# ── Main loop ────────────────────────────────────────────────────────────────
print("\nSTARTING PIPELINE LOOP (Ctrl-C to stop)\n")

while True:
    current_rows = live_row_count()

    # FIX: only retrain when enough NEW live rows have accumulated
    rows_since_train = current_rows - last_trained_at_row
    if rows_since_train >= RETRAIN_EVERY:
        print(f"\n{rows_since_train} new live rows — retraining model...")
        if run("train_model.py") == 0:
            last_trained_at_row = current_rows
        else:
            print("WARNING: retraining failed; keeping previous model.")
    else:
        print(f"\nSkipping retrain ({rows_since_train}/{RETRAIN_EVERY} new rows)")

    # Step 1 — extract thresholds from live (or static fallback) data
    run("threshold_extract.py")

    # Step 2 — push updated thresholds to Blynk
    run("upload_threshold.py")

    # Step 3 — check latest reading against thresholds; send alerts
    run("warning_check.py")

    # Step 4 — run live prediction so you can see model output in console
    if current_rows > 0:
        run("predict_live.py")
    else:
        print("predict_live.py skipped — no live data yet")

    print(f"\nWaiting {LOOP_INTERVAL} s...\n{'─'*50}")
    time.sleep(LOOP_INTERVAL)