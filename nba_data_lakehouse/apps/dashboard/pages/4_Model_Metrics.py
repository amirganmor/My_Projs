"""Page: Model Metrics — MLflow experiment tracking summary."""
import streamlit as st
import os
import requests

st.set_page_config(page_title="Model Metrics", layout="wide")
st.title("ML Model Metrics")
st.markdown("Summary of model training experiments logged to MLflow.")

MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5001")

st.markdown(f"**MLflow Tracking URI:** [{MLFLOW_URI}]({MLFLOW_URI.replace('mlflow', 'localhost')})")

def fetch_experiments():
    try:
        resp = requests.get(f"{MLFLOW_URI}/api/2.0/mlflow/experiments/search", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("experiments", [])
    except Exception:
        pass
    return []

def fetch_runs(experiment_id: str):
    try:
        resp = requests.post(
            f"{MLFLOW_URI}/api/2.0/mlflow/runs/search",
            json={"experiment_ids": [experiment_id], "max_results": 50},
            timeout=5,
        )
        if resp.status_code == 200:
            return resp.json().get("runs", [])
    except Exception:
        pass
    return []

experiments = fetch_experiments()

if not experiments:
    st.info("No MLflow experiments found. Run the training pipeline first.")
    st.markdown("""
    **Expected experiments after pipeline:**
    - `nba_player_value_model` — Predicting salary from performance features
    - `nba_player_improvement_model` — Predicting breakout seasons
    """)
    st.stop()

for exp in experiments:
    if exp.get("name", "").startswith("Default"):
        continue
    st.subheader(f"Experiment: {exp['name']}")
    runs = fetch_runs(exp["experiment_id"])

    if not runs:
        st.write("No runs yet.")
        continue

    import pandas as pd
    rows = []
    for run in runs:
        info = run.get("info", {})
        data = run.get("data", {})
        metrics = {m["key"]: round(m["value"], 4) for m in data.get("metrics", [])}
        params = {p["key"]: p["value"] for p in data.get("params", [])}
        rows.append({
            "Run Name": info.get("run_name", ""),
            "Status": info.get("status", ""),
            "Model": params.get("model_type", ""),
            **metrics,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
