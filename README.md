# 🌾 Shashya Rakkhak — Smart Grain Storage Spoilage Prevention System

**Shashya Rakkhak** ("Crop Protector") is an IoT + Machine Learning system that monitors grain storage conditions in real time and predicts spoilage risk before it happens. It combines an ESP8266-based sensor node, a self-updating ML pipeline, and cloud dashboard/alerting via Blynk and Twilio.

---

## 📋 Table of Contents

- [How It Works](#-how-it-works)
- [Hardware](#-hardware)
- [Repository Structure](#-repository-structure)
- [Setup](#-setup)
- [Running the System](#-running-the-system)
- [ML Model](#-ml-model)
- [Blynk Virtual Pin Map](#-blynk-virtual-pin-map)
- [Roadmap](#-roadmap)
- [License](#-license)

---

## 🧠 How It Works

```
 ┌────────────────┐     Serial CSV      ┌──────────────┐     live_dataset.csv     ┌──────────────────┐
 │  ESP8266 Node   │ ──────────────────► │  logger.py   │ ────────────────────────► │  ML Pipeline     │
 │ (DHT11 x2, MQ135)│                    │ (feature eng)│                          │ (auto_pipeline.py)│
 └────────┬────────┘                     └──────────────┘                          └────────┬─────────┘
          │  Blynk (WiFi)                                                                    │
          ▼                                                                                  ▼
 ┌────────────────┐   thresholds (V20-22)   ┌────────────────────┐   prediction (V45)  ┌──────────────┐
 │  Blynk Cloud    │ ◄────────────────────── │ threshold_extract.py│                    │predict_live.py│
 │  Dashboard/App  │ ────────────────────────► upload_threshold.py │ ◄──────────────────┘
 │  + SMS (Twilio) │   alerts (V31, events)  │ warning_check.py    │
 └────────────────┘                          └────────────────────┘
```

1. **Sensing** — An ESP8266 reads two DHT11 sensors (temperature/humidity at two points in the grain bin) and an MQ135 gas sensor, computes a temperature gradient, gas/humidity trend, and a rule-based confidence/risk score, then streams a 9-value CSV line over serial every 5 seconds.
2. **Logging** (`logger.py`) — Reads the serial stream, derives the two extra features the ML model needs (`spatial_score`, `gas_accel`), and appends each reading to `live_dataset.csv`.
3. **Learning** (`train_model.py`) — A `RandomForestClassifier` is trained on a labeled dataset of grain-storage conditions (`bd_grain_storage_risk_dataset.csv`) across multiple crops (rice, wheat, garlic, etc.) to classify spoilage risk into 5 classes: `Safe`, `Low`, `Moderate`, `High`, `Critical`.
4. **Automation** (`auto_pipeline.py`) — Orchestrates the full loop every 60 seconds: retrains the model once enough new live rows accumulate, recomputes thresholds, pushes them to Blynk, checks for warnings, and runs a live prediction.
5. **Adaptive thresholds** (`threshold_extract.py`) — Recomputes gas/humidity/gradient thresholds from the mean of recent high-risk readings (falling back to the static dataset when live data is too sparse), then pushes them to the ESP8266 via Blynk virtual pins so the device's own rule-based logic stays in sync with what the model is learning.
6. **Alerting** (`warning_check.py`) — Compares the latest live reading against the current thresholds and fires a Blynk notification + optional SMS (via Twilio) if any threshold is exceeded.
7. **On-device decision** (`sketch_may8a.ino`) — The ESP8266 independently combines sensor-based risk *and* the AI prediction it receives back from `predict_live.py` (via virtual pin `V45`) to decide whether to trigger the relay/buzzer, so the system still protects the grain even if the cloud pipeline is briefly unreachable.

## 🔌 Hardware

| Component            | Pin       | Purpose                              |
|-----------------------|-----------|---------------------------------------|
| DHT11 #1              | D5        | Temperature/humidity, point A         |
| DHT11 #2              | D6        | Temperature/humidity, point B         |
| MQ135 gas sensor      | A0        | Ammonia/CO₂-type spoilage gas level   |
| Relay                 | D1        | Ventilation fan / exhaust control     |
| LED                   | D2        | Visual warning indicator              |
| Piezo buzzer          | D7        | Audible warning                       |

Board: ESP8266 (NodeMCU or similar), using `ESP8266WiFi`, `BlynkSimpleEsp8266`, and `DHT` libraries.

## 📁 Repository Structure

```
shashya-rakkhak/
├── firmware/
│   └── sketch_may8a.ino          # ESP8266 firmware
├── bd_grain_storage_risk_dataset.csv  # Labeled training dataset
├── train_model.py                # Trains RandomForestClassifier → grain_model.pkl
├── logger.py                     # Serial → live_dataset.csv
├── threshold_extract.py          # Computes adaptive thresholds → thresholds.txt
├── upload_threshold.py           # Pushes thresholds to Blynk (V20-V22)
├── warning_check.py              # Threshold breach alerts (Blynk + Twilio SMS)
├── predict_live.py               # Live risk prediction from latest sensor row
├── auto_pipeline.py              # Orchestrates the full loop on a timer
├── requirements.txt
├── .env.example
└── .gitignore
```

> `live_dataset.csv`, `thresholds.txt`, and `grain_model.pkl` are generated at runtime and are git-ignored — they're recreated the first time you run the pipeline.

## ⚙️ Setup

```bash
git clone https://github.com/<your-username>/shashya-rakkhak.git
cd shashya-rakkhak
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# then edit .env and set BLYNK_TOKEN (and SERIAL_PORT / Twilio vars if needed)
```

**Firmware:** open `firmware/sketch_may8a.ino` in the Arduino IDE, fill in your own `BLYNK_TEMPLATE_ID`, `BLYNK_TEMPLATE_NAME`, `BLYNK_AUTH_TOKEN`, WiFi `ssid`/`pass`, and flash it to the ESP8266.

## ▶️ Running the System

**Terminal 1 — logger** (keep running while the ESP8266 is connected):
```bash
python logger.py
```

**Terminal 2 — pipeline** (initial training + the 60s automation loop):
```bash
python auto_pipeline.py
```

This runs `train_model.py` once on startup, then loops: retrain when `≥50` new live rows have accumulated → `threshold_extract.py` → `upload_threshold.py` → `warning_check.py` → `predict_live.py`.

You can also run any step individually, e.g. `python predict_live.py` to see the current risk prediction for the latest logged reading.

## 🤖 ML Model

- **Algorithm:** `RandomForestClassifier` (100 trees, max depth 8)
- **Features (9):** `temp`, `humidity`, `gas`, `gradient`, `gas_trend`, `humidity_trend`, `confidence`, `spatial_score`, `gas_accel`
- **Target classes:** `Safe`, `Low_Spoilage_Risk`, `Moderate_Spoilage_Risk`, `High_Spoilage_Risk`, `Critical_Spoilage`
- **Training data:** multi-crop synthetic/lab dataset (`bd_grain_storage_risk_dataset.csv`) covering rice paddy, wheat, garlic, and other stored crops
- **Retraining:** automatic, every 50 new live rows accumulated in `live_dataset.csv`, so the model adapts to the specific storage environment it's deployed in

## 📡 Blynk Virtual Pin Map

| Pin  | Direction | Meaning                                  |
|------|-----------|-------------------------------------------|
| V0   | out       | Average temperature                       |
| V1   | out       | Average humidity                          |
| V2   | out       | Filtered gas level                        |
| V3   | out       | Temperature gradient                      |
| V4   | out       | Confidence score                          |
| V5   | out       | AI risk level (0–4)                       |
| V6   | out       | Sensor-based future risk (0–3)            |
| V7   | in        | Manual relay override                     |
| V8   | in        | Manual test-warning trigger               |
| V20–V22 | in     | Gas / humidity / gradient thresholds (from ML pipeline) |
| V23–V25 | out    | Threshold mirrors (display only)          |
| V30  | out       | WiFi status                               |
| V31  | out       | Warning/status message                    |
| V45  | in        | AI prediction label (from `predict_live.py`) |

## 🗺️ Roadmap

- [ ] Web dashboard (beyond Blynk) for historical trend charts
- [ ] Support for multiple storage bins / multi-node deployment
- [ ] Model versioning and accuracy tracking across retrains
- [ ] Solar-powered / battery deployment for off-grid storage sites

## 📄 License

Released under the [MIT License](LICENSE).
