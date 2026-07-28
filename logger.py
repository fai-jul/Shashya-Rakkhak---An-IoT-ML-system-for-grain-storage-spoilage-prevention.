"""
logger.py — Fixed version
CHANGES:
  - Computes spatial_score and gas_accel from incoming serial data
    so live rows match the 9-feature model exactly.
  - Robust port auto-detection with retry.
  - Guards against partial/corrupt serial lines.
"""

import os
import time
from datetime import datetime

import pandas as pd
import serial
import serial.tools.list_ports
from dotenv import load_dotenv

load_dotenv()

DEFAULT_PORTS = ["COM5", "COM4", "COM3", "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0"]
SERIAL_PORT = os.getenv("SERIAL_PORT", "").strip()
BAUD = int(os.getenv("SERIAL_BAUD", "115200"))

csv_file = "live_dataset.csv"

# FIX: columns now include spatial_score and gas_accel so live rows
#      match the trained model's expected feature set exactly.
columns = [
    "temp",
    "humidity",
    "gas",
    "gradient",
    "gas_trend",
    "humidity_trend",
    "confidence",
    "current_risk",
    "future_risk",
    "spatial_score",   # <-- ADDED: derived from gradient
    "gas_accel",       # <-- ADDED: derived from gas_trend delta
    "time",
]

if not os.path.exists(csv_file) or os.path.getsize(csv_file) == 0:
    pd.DataFrame(columns=columns).to_csv(csv_file, index=False)

ser = None
prev_gas_trend = 0.0   # used to compute gas_accel each cycle


def open_serial():
    global ser
    ports = []
    if SERIAL_PORT:
        ports.append(SERIAL_PORT)
    ports.extend(DEFAULT_PORTS)
    ports.extend([info.device for info in serial.tools.list_ports.comports()])
    ports = list(dict.fromkeys(ports))  # deduplicate, preserve order

    if not ports:
        print("No serial ports detected.")
        return

    for port in ports:
        try:
            print(f"Trying serial port {port}...")
            ser = serial.Serial(port, BAUD, timeout=1)
            print(f"SERIAL PORT OPENED: {port}")
            return
        except Exception as e:
            print(f"  SERIAL OPEN ERROR ({port}): {e}")
            ser = None

    print("Unable to open any serial port. Will retry in 5 s.")


open_serial()
print("LOGGER STARTED")

while True:
    if ser is None:
        open_serial()
        time.sleep(5)
        continue

    try:
        raw = ser.readline()
        line = raw.decode(errors="ignore").strip()

        if not line:
            continue

        # FIX: filter out any non-CSV debug lines the ESP might emit
        parts = [v.strip() for v in line.split(",")]
        if len(parts) != 9:
            print(f"SKIP ({len(parts)} fields): {line}")
            continue

        # Parse the 9 values sent by the Arduino
        (temp, humidity, gas, gradient,
         gas_trend, humidity_trend, confidence,
         current_risk, future_risk) = [float(p) for p in parts]

        # ----------------------------------------------------------------
        # FIX: derive the two features the model was trained on but the
        #      Arduino never sends directly.
        #
        #  spatial_score — normalised gradient in [0,1] capped at 10 °C
        spatial_score = min(gradient / 10.0, 1.0)

        #  gas_accel — change in gas_trend between consecutive readings
        #              (approximates second derivative of gas level)
        gas_accel = gas_trend - prev_gas_trend
        # ----------------------------------------------------------------

        row = {
            "temp":           temp,
            "humidity":       humidity,
            "gas":            gas,
            "gradient":       gradient,
            "gas_trend":      gas_trend,
            "humidity_trend": humidity_trend,
            "confidence":     confidence,
            "current_risk":   current_risk,
            "future_risk":    future_risk,
            "spatial_score":  round(spatial_score, 4),
            "gas_accel":      round(gas_accel, 4),
            "time":           datetime.now().isoformat(),
        }

        try:
            df = pd.read_csv(csv_file)
        except (pd.errors.EmptyDataError, FileNotFoundError):
            df = pd.DataFrame(columns=columns)

        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

        if len(df) > 5000:
            df = df.tail(5000)

        df.to_csv(csv_file, index=False)
        prev_gas_trend = gas_trend
        print(row)

    except ValueError as e:
        print(f"PARSE ERROR: {e} | line={line!r}")
    except Exception as e:
        print(f"LOGGER ERROR: {e}")
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        ser = None
        time.sleep(5)