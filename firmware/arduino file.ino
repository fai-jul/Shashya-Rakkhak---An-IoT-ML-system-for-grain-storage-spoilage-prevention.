/************************************************************
 SMART GRAIN MONITOR — FINAL STABLE v5.0

ways 0
 - All previous fixes from v4.0 kept intact
************************************************************/

#define BLYNK_TEMPLATE_ID   "id"
#define BLYNK_TEMPLATE_NAME "Smart Grain Monitor"
#define BLYNK_AUTH_TOKEN    "token"

#include <ESP8266WiFi.h>
#include <BlynkSimpleEsp8266.h>
#include <DHT.h>
#include <math.h>

/************************************************************
 WIFI
************************************************************/
char ssid[] = "YOUR_WIFI_SSID";
char pass[] = "YOUR_WIFI_PASSWORD";

/************************************************************
 DHT CONFIG
************************************************************/
#define DHTTYPE  DHT11
#define DHT1_PIN D5
#define DHT2_PIN D6

DHT dht1(DHT1_PIN, DHTTYPE);
DHT dht2(DHT2_PIN, DHTTYPE);

/************************************************************
 MQ135
************************************************************/
#define MQ135_PIN A0

/************************************************************
 OUTPUTS
************************************************************/
#define RELAY_PIN D1
#define LED_PIN   D2
#define PIEZO_PIN D7

/************************************************************
 SENSOR VARIABLES
************************************************************/
float t1 = 0, t2 = 0;
float h1 = 0, h2 = 0;
float avgTemp      = 0;
float avgHumidity  = 0;
float tempGradient = 0;
int   gasRaw       = 0;

/************************************************************
 GAS FILTER (moving average)
************************************************************/
const int FILTER_SIZE = 10;
int   gasSamples[FILTER_SIZE];
int   gasIndex    = 0;
float filteredGas = 0;

/************************************************************
 TREND VARIABLES
************************************************************/
float prevGas       = 0;
float prevHumidity  = 0;
float gasTrend      = 0;
float humidityTrend = 0;

/************************************************************
 ADAPTIVE THRESHOLDS
 Defaults match thresholds.txt — overwritten via syncVirtual
************************************************************/
float gasThreshold      = 163.0;
float humidityThreshold = 55.0;
float gradientThreshold = 0.59;

/************************************************************
 RISK & CONFIDENCE
************************************************************/
int currentRisk     = 0;
int futureRisk      = 0;
int confidenceScore = 0;

/************************************************************
 AI PREDICTION FROM PYTHON (written to V45 by predict_live.py)
 aiRiskLevel:
   0 = Safe
   1 = Low_Spoilage_Risk
   2 = Moderate_Spoilage_Risk
   3 = High_Spoilage_Risk
   4 = Critical_Spoilage
************************************************************/
String aiPredictionLabel = "Unknown";  // raw string from V45
int    aiRiskLevel       = 0;          // mapped to 0-4

// Map the prediction string to an integer level
int mapLabelToLevel(String label) {
    label.trim();
    if (label == "Safe")                   return 0;
    if (label == "Low_Spoilage_Risk")      return 1;
    if (label == "Moderate_Spoilage_Risk") return 2;
    if (label == "High_Spoilage_Risk")     return 3;
    if (label == "Critical_Spoilage")      return 4;
    return 0;  // default to safe if unknown
}

/************************************************************
 STATES
************************************************************/
bool manualRelay   = false;
bool testWarning   = false;
bool warningActive = false;

/************************************************************
 TIMER
************************************************************/
BlynkTimer timer;

/************************************************************
 BLYNK VIRTUAL PIN HANDLERS
************************************************************/

// V7 = RelayControl — manual relay ON/OFF
BLYNK_WRITE(V7) {
    manualRelay = param.asInt();
    if (manualRelay) {
        digitalWrite(RELAY_PIN, LOW);
        digitalWrite(LED_PIN, LOW);
        noTone(PIEZO_PIN);
        Blynk.virtualWrite(V31, "MANUAL: Relay ON");
    } else {
        digitalWrite(RELAY_PIN, HIGH);
        Blynk.virtualWrite(V31, "SYSTEM OK");
    }
}

// V8 = Piezzo Pin — manual test warning button (Switch mode)
BLYNK_WRITE(V8) {
    testWarning = param.asInt();
    if (testWarning) {
        tone(PIEZO_PIN, 1000);
        digitalWrite(LED_PIN, HIGH);
        digitalWrite(RELAY_PIN, LOW);
        Blynk.virtualWrite(V31, "!! TEST WARNING: Manual V8 trigger");
        Blynk.logEvent("grain_warning", "TEST WARNING triggered from V8");
    } else {
        noTone(PIEZO_PIN);
        digitalWrite(LED_PIN, LOW);
        if (!manualRelay) digitalWrite(RELAY_PIN, HIGH);
        if (!warningActive) Blynk.virtualWrite(V31, "SYSTEM OK");
    }
}

// V20/V21/V22 = thresholds written by Python pipeline
BLYNK_WRITE(V20) { gasThreshold      = param.asFloat(); }
BLYNK_WRITE(V21) { humidityThreshold = param.asFloat(); }
BLYNK_WRITE(V22) { gradientThreshold = param.asFloat(); }

// V45 = AI prediction label written by predict_live.py every 60s
// Example values: "Safe", "Moderate_Spoilage_Risk", "Critical_Spoilage"
BLYNK_WRITE(V45) {
    aiPredictionLabel = param.asStr();
    aiRiskLevel       = mapLabelToLevel(aiPredictionLabel);
    Serial.print("AI prediction received: ");
    Serial.print(aiPredictionLabel);
    Serial.print(" → level ");
    Serial.println(aiRiskLevel);
}

/************************************************************
 BLYNK CONNECTED — sync all input pins on every reconnect
************************************************************/
BLYNK_CONNECTED() {
    Blynk.syncVirtual(V7);
    Blynk.syncVirtual(V8);
    Blynk.syncVirtual(V20);  // gas threshold
    Blynk.syncVirtual(V21);  // humidity threshold
    Blynk.syncVirtual(V22);  // gradient threshold
    Blynk.syncVirtual(V45);  // last AI prediction label
    Blynk.syncVirtual(V46);  // last AI confidence score
}

/************************************************************
 SEND WARNING
************************************************************/
void sendWarning(String msg) {
    if (!Blynk.connected()) return;
    Blynk.virtualWrite(V31, msg);
    Blynk.logEvent("grain_warning", msg);
}

/************************************************************
 READ SENSORS
************************************************************/
bool readSensors() {
    t1     = dht1.readTemperature();
    h1     = dht1.readHumidity();
    t2     = dht2.readTemperature();
    h2     = dht2.readHumidity();
    gasRaw = analogRead(MQ135_PIN);
    if (isnan(t1) || isnan(h1) || isnan(t2) || isnan(h2)) return false;
    return true;
}

/************************************************************
 FILTER GAS
************************************************************/
void filterGas() {
    gasSamples[gasIndex] = gasRaw;
    gasIndex++;
    if (gasIndex >= FILTER_SIZE) gasIndex = 0;
    long sum = 0;
    for (int i = 0; i < FILTER_SIZE; i++) sum += gasSamples[i];
    filteredGas = sum / (float)FILTER_SIZE;
}

/************************************************************
 COMPUTE FEATURES
************************************************************/
void computeFeatures() {
    avgTemp       = (t1 + t2) / 2.0;
    avgHumidity   = (h1 + h2) / 2.0;
    tempGradient  = fabs(t1 - t2);
    gasTrend      = filteredGas - prevGas;
    humidityTrend = avgHumidity - prevHumidity;
}

/************************************************************
 COMPUTE CONFIDENCE SCORE
************************************************************/
void computeConfidence() {
    confidenceScore = 0;
    if (filteredGas   > gasThreshold)      confidenceScore += 3;
    if (avgHumidity   > humidityThreshold) confidenceScore += 2;
    if (tempGradient  > gradientThreshold) confidenceScore += 2;
    if (gasTrend      > 0)                 confidenceScore += 1;
    if (humidityTrend > 0)                 confidenceScore += 1;
}

/************************************************************
 COMPUTE CURRENT RISK (sensor-based 0-3)
************************************************************/
void computeCurrentRisk() {
    currentRisk = 0;
    if (filteredGas > gasThreshold)
        currentRisk = 1;
    if (filteredGas > gasThreshold && avgHumidity > humidityThreshold)
        currentRisk = 2;
    if (filteredGas > gasThreshold && avgHumidity > humidityThreshold
        && tempGradient > gradientThreshold)
        currentRisk = 3;
}

/************************************************************
 COMPUTE FUTURE RISK
************************************************************/
void computeFutureRisk() {
    futureRisk = currentRisk;
    if (gasTrend > 10 && humidityTrend > 1) {
        futureRisk++;
        if (futureRisk > 3) futureRisk = 3;
    }
}

/************************************************************
 SAFETY OVERRIDE
************************************************************/
bool safetyOverride() {
    if (filteredGas > 800) return true;
    if (avgHumidity > 90)  return true;
    return false;
}

/************************************************************
 RELAY CONTROL — now uses BOTH sensor risk AND AI prediction
 
 Decision priority (highest to lowest):
   1. Manual relay (V7) — user always wins
   2. Test button (V8) — test mode
   3. Safety override — gas>800 or humidity>90 (hardware limit)
   4. AI says High or Critical — model-driven alert
   5. Sensor-based risk >= 2 — threshold-based alert
   6. Normal — all OK
************************************************************/
void controlRelay() {
    if (manualRelay || testWarning) return;

    bool   warningNow = false;
    String warningMsg = "";

    // Priority 3: hardware safety limit
    if (safetyOverride()) {
        digitalWrite(RELAY_PIN, LOW);
        digitalWrite(LED_PIN, HIGH);
        tone(PIEZO_PIN, 1500);
        warningNow = true;
        warningMsg = "CRITICAL! Gas=" + String((int)filteredGas)
                   + " Hum=" + String((int)avgHumidity) + "%";

    // Priority 4: AI model says High or Critical spoilage
    } else if (aiRiskLevel >= 3) {
        digitalWrite(RELAY_PIN, LOW);
        digitalWrite(LED_PIN, HIGH);
        // Critical = fast beep, High = slow beep
        tone(PIEZO_PIN, aiRiskLevel == 4 ? 1500 : 1000);
        warningNow = true;
        warningMsg = "AI: " + aiPredictionLabel
                   + " Gas=" + String((int)filteredGas)
                   + " Hum=" + String((int)avgHumidity) + "%";

    // Priority 5: sensor thresholds exceeded
    } else if (futureRisk >= 2 && confidenceScore >= 3) {
        digitalWrite(RELAY_PIN, LOW);
        digitalWrite(LED_PIN, HIGH);
        tone(PIEZO_PIN, 800);
        warningNow = true;
        warningMsg = "SENSOR WARNING! Risk=" + String(futureRisk)
                   + " Conf=" + String(confidenceScore);

    // Priority 6: all OK
    } else {
        digitalWrite(RELAY_PIN, HIGH);
        digitalWrite(LED_PIN, LOW);
        noTone(PIEZO_PIN);
        warningNow = false;
    }

    // Fire alert ONCE per warning event
    if (warningNow && !warningActive) {
        sendWarning(warningMsg);
        warningActive = true;
    }

    // Clear when back to normal
    if (!warningNow) {
        if (warningActive) Blynk.virtualWrite(V31, "SYSTEM OK");
        warningActive = false;
    }
}

/************************************************************
 SEND TO BLYNK
 V5 now shows aiRiskLevel (0-4) — matches your 5-class model
 V6 shows futureRisk (0-3) — sensor-based prediction
 V31 NOT touched here — owned by sendWarning()/controlRelay()
************************************************************/
void sendToBlynk() {
    if (!Blynk.connected()) return;

    Blynk.virtualWrite(V0,  avgTemp);
    Blynk.virtualWrite(V1,  avgHumidity);
    Blynk.virtualWrite(V2,  filteredGas);
    Blynk.virtualWrite(V3,  tempGradient);
    Blynk.virtualWrite(V4,  confidenceScore);
    Blynk.virtualWrite(V5,  aiRiskLevel);    // 0-4 from AI model
    Blynk.virtualWrite(V6,  futureRisk);     // 0-3 sensor-based
    Blynk.virtualWrite(V30, WiFi.status());

    // Display-only threshold mirrors
    Blynk.virtualWrite(V23, gasThreshold);
    Blynk.virtualWrite(V24, humidityThreshold);
    Blynk.virtualWrite(V25, gradientThreshold);

    // V31 NOT written here — would overwrite warnings
    // V40-V46 NOT written here — owned by predict_live.py
}

/************************************************************
 STREAM CSV TO SERIAL — exactly 9 values
************************************************************/
void streamCSV() {
    Serial.print(avgTemp);         Serial.print(",");
    Serial.print(avgHumidity);     Serial.print(",");
    Serial.print(filteredGas);     Serial.print(",");
    Serial.print(tempGradient);    Serial.print(",");
    Serial.print(gasTrend);        Serial.print(",");
    Serial.print(humidityTrend);   Serial.print(",");
    Serial.print(confidenceScore); Serial.print(",");
    Serial.print(currentRisk);     Serial.print(",");
    Serial.println(futureRisk);
}

/************************************************************
 STORE PREVIOUS VALUES
************************************************************/
void storePrevious() {
    prevGas      = filteredGas;
    prevHumidity = avgHumidity;
}

/************************************************************
 MAIN TASK — every 5 seconds
************************************************************/
void mainTask() {
    if (!readSensors()) return;
    filterGas();
    computeFeatures();
    computeConfidence();
    computeCurrentRisk();
    computeFutureRisk();
    controlRelay();
    sendToBlynk();
    streamCSV();
    storePrevious();
}

/************************************************************
 SETUP
************************************************************/
void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.println("BOOT");

    pinMode(RELAY_PIN, OUTPUT);
    pinMode(LED_PIN,   OUTPUT);
    pinMode(PIEZO_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, HIGH);
    digitalWrite(LED_PIN,   LOW);
    noTone(PIEZO_PIN);

    dht1.begin();
    dht2.begin();
    for (int i = 0; i < FILTER_SIZE; i++) gasSamples[i] = 0;

    Serial.println("WARMUP");
    delay(10000);

    WiFi.begin(ssid, pass);
    Serial.print("WIFI_CONNECTING");
    int tries = 0;
    while (WiFi.status() != WL_CONNECTED && tries < 30) {
        delay(500);
        Serial.print(".");
        tries++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("WIFI_OK");
        Blynk.config(BLYNK_AUTH_TOKEN);
        Blynk.connect(3000);
    } else {
        Serial.println("WIFI_FAIL_OFFLINE_MODE");
    }

    timer.setInterval(5000L, mainTask);
    Serial.println("READY");
}

/************************************************************
 LOOP
************************************************************/
void loop() {
    if (Blynk.connected()) Blynk.run();
    timer.run();
}
