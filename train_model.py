import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
import joblib

df = pd.read_csv("bd_grain_storage_risk_dataset.csv")

X = df[
[
    "temp",
    "humidity",
    "gas",
    "gradient",
    "gas_trend",
    "humidity_trend",
    "confidence",
    "spatial_score",
    "gas_accel"
]]

y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

model = RandomForestClassifier(
    n_estimators=100,
    max_depth=8,
    random_state=42
)

model.fit(X_train, y_train)

pred = model.predict(X_test)

print(classification_report(y_test, pred))

joblib.dump(model, "grain_model.pkl")

print("MODEL SAVED")