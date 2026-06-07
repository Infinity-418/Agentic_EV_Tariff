import os
import shutil
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

workspace = "/Users/anubhav/Documents/EV_Tariff_Optimization"
submission_dir = os.path.join(workspace, "Google_Drive_Submission")
graphs_dir = os.path.join(submission_dir, "graphs")
outputs_dir = os.path.join(submission_dir, "outputs")

# Create folders
os.makedirs(submission_dir, exist_ok=True)
os.makedirs(graphs_dir, exist_ok=True)
os.makedirs(outputs_dir, exist_ok=True)

print("Copying notebook and figures...")

# Copy notebook
nb_src = os.path.join(workspace, "EV_Tariff_optimization_24124005.ipynb")
if os.path.exists(nb_src):
    shutil.copy2(nb_src, os.path.join(submission_dir, "EV_Tariff_optimization_24124005.ipynb"))
    print("Notebook copied successfully.")
else:
    print(f"Error: Notebook not found at {nb_src}")

# Copy graphs
plots_src = os.path.join(workspace, "plots")
if os.path.exists(plots_src):
    copied_plots = 0
    for filename in os.listdir(plots_src):
        if filename.endswith(".png"):
            shutil.copy2(os.path.join(plots_src, filename), os.path.join(graphs_dir, filename))
            copied_plots += 1
    print(f"Copied {copied_plots} figures to graphs/ folder.")
else:
    print(f"Error: plots folder not found at {plots_src}")

print("Re-running GBR model and optimization to generate outputs...")

# Re-run data processing and save CSVs
ACN_PATH    = os.path.join(workspace, "acndata_sessions.json")
URBANEV_ZIP = os.path.join(workspace, "ST-EVCDP-main.zip")

try:
    import ijson
    import zipfile
except ImportError:
    print("Prerequisites missing. Run save_plots.py first.")
    exit(1)

# Grid cost helper
def get_grid_cost(dt):
    h = dt.hour
    if (9 <= h < 12) or (18 <= h < 21):
        return 10.0
    elif 0 <= h < 6:
        return 4.0
    else:
        return 7.0

# 1. Load ACN Data
acn_items = []
with open(ACN_PATH, "rb") as f:
    first_char = f.read(1).decode("utf-8", errors="ignore")
    while first_char.isspace():
        first_char = f.read(1).decode("utf-8", errors="ignore")
    f.seek(0)
    parser_prefix = "item" if first_char == "[" else "_items.item"
    if first_char == "{":
        for prefix, event, _ in ijson.parse(f):
            if event == "start_array" and prefix in ("_items", "items"):
                parser_prefix = f"{prefix}.item"
                break
        f.seek(0)
    try:
        for item in ijson.items(f, parser_prefix):
            acn_items.append(item)
    except ijson.common.IncompleteJSONError:
        pass

acn_rows = []
for item in acn_items:
    try:
        conn_t = pd.to_datetime(item["connectionTime"],  utc=True).tz_localize(None)
        disc_t = pd.to_datetime(item["disconnectTime"],  utc=True).tz_localize(None)
    except Exception:
        continue
    duration = (disc_t - conn_t).total_seconds() / 3600.0
    if duration <= 0:
        continue
    done_raw = item.get("doneChargingTime")
    if done_raw:
        try:
            done_t = pd.to_datetime(done_raw, utc=True).tz_localize(None)
            charging_duration = max((done_t - conn_t).total_seconds() / 3600.0, 0.0)
        except Exception:
            charging_duration = duration
    else:
        charging_duration = duration
    kwh  = float(item.get("kWhDelivered", 0.0) or 0.0)
    ui   = (item.get("userInputs") or [{}])[0]
    wh_req    = float(ui.get("whRequested") or ui.get("WhRequested") or kwh * 1000)
    min_avail = float(ui.get("minutesAvailable") or duration * 60.0)
    acn_rows.append({
        "session_id":             item.get("sessionID", ""),
        "station_id":             item.get("stationID", ""),
        "space_id":               item.get("spaceID", ""),
        "connection_time":        conn_t,
        "disconnect_time":        disc_t,
        "session_duration_hours": duration,
        "charging_duration_hours": min(charging_duration, duration),
        "kwh_delivered":          kwh,
        "kwh_requested":          wh_req / 1000.0,
        "minutes_available":      min_avail,
        "user_id":                item.get("userID", 0),
        "site_id":                item.get("siteID", "")
    })

acn_df = pd.DataFrame(acn_rows)
dur_cap = acn_df["session_duration_hours"].quantile(0.99)
acn_df["session_duration_hours"]  = acn_df["session_duration_hours"].clip(upper=dur_cap)
acn_df["charging_duration_hours"] = acn_df["charging_duration_hours"].clip(upper=dur_cap)
acn_df["charger_utilization_rate"] = (acn_df["charging_duration_hours"] / acn_df["session_duration_hours"]).clip(0, 1)

# 2. Load UrbanEV Data
with zipfile.ZipFile(URBANEV_ZIP) as z:
    root = next((n.replace("occupancy.csv","") for n in z.namelist() if n.endswith("occupancy.csv")), None)
    def read_csv(name):
        with z.open(root + name) as f:
            return pd.read_csv(f)
    urbanev_occ   = read_csv("occupancy.csv")
    urbanev_price = read_csv("price.csv")
    urbanev_info  = read_csv("information.csv")
    urbanev_time  = read_csv("time.csv")

urbanev_time["timestamp"] = pd.to_datetime(urbanev_time[["year","month","day","hour","minute"]])
ts_map = urbanev_time["timestamp"].reset_index().rename(columns={"index":"time_idx"})

occ_melted   = urbanev_occ.rename(columns={"timestamp":"time_idx"}).melt(id_vars="time_idx", var_name="zone_id", value_name="occupancy")
price_melted = urbanev_price.rename(columns={"timestamp":"time_idx"}).melt(id_vars="time_idx", var_name="zone_id", value_name="price_baseline")
occ_melted["zone_id"]   = pd.to_numeric(occ_melted["zone_id"])
price_melted["zone_id"] = pd.to_numeric(price_melted["zone_id"])

occ_melted   = occ_melted.merge(ts_map,   on="time_idx")
price_melted = price_melted.merge(ts_map, on="time_idx")
flat_df = occ_melted.merge(price_melted[["zone_id","timestamp","price_baseline"]], on=["zone_id","timestamp"], how="left")

info_r  = urbanev_info.rename(columns={"grid":"zone_id","CBD":"is_cbd","count":"capacity"})
flat_df = flat_df.merge(info_r[["zone_id","is_cbd","capacity"]], on="zone_id", how="left")
flat_df["hour"]               = flat_df["timestamp"].dt.hour
flat_df["day_of_week"]        = flat_df["timestamp"].dt.dayofweek
flat_df["is_weekend"]         = flat_df["day_of_week"].isin([5, 6])
flat_df["occupancy_rate"]     = (flat_df["occupancy"] / flat_df["capacity"]).clip(0, 1)
flat_df["grid_cost_kwh"]      = flat_df["timestamp"].apply(get_grid_cost)
flat_df["queue_length_proxy"] = np.where(
    flat_df["occupancy_rate"] > 0.85,
    (flat_df["occupancy_rate"] - 0.85) * flat_df["capacity"] * 1.5,
    0.0
)
flat_df = flat_df.sort_values(["zone_id","timestamp"]).reset_index(drop=True)

# GBR Feature Engineering
flat_df_sorted = flat_df.sort_values(["zone_id","timestamp"]).reset_index(drop=True)
for lag in [1, 3, 6, 12]:
    flat_df_sorted[f"lag_{lag}"] = flat_df_sorted.groupby("zone_id")["occupancy_rate"].shift(lag)
flat_df_sorted["roll_mean_3"] = flat_df_sorted.groupby("zone_id")["lag_1"].transform(lambda x: x.rolling(3).mean())
flat_df_sorted["roll_mean_6"] = flat_df_sorted.groupby("zone_id")["lag_1"].transform(lambda x: x.rolling(6).mean())

features = ["hour","day_of_week","is_cbd","lag_1","lag_3","lag_6","lag_12",
            "roll_mean_3","roll_mean_6","grid_cost_kwh"]
target   = "occupancy_rate"
ml_data  = flat_df_sorted.dropna().reset_index(drop=True)
X, y     = ml_data[features], ml_data[target]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

demand_model = GradientBoostingRegressor(n_estimators=100, max_depth=5, learning_rate=0.1, random_state=42)
demand_model.fit(X_train, y_train)

# Generate and save predictions CSV
y_pred = np.clip(demand_model.predict(X_test), 0.0, 1.0)
def congestion_prob(occ, threshold=0.80, steepness=20.0):
    return 1.0 / (1.0 + np.exp(-steepness * (occ - threshold)))

congestion_probs = congestion_prob(y_pred)
avg_kwh_per_pile = acn_df["kwh_delivered"].mean()

pred_df = pd.DataFrame({
    "timestamp":              ml_data.loc[X_test.index, "timestamp"],
    "zone_id":                ml_data.loc[X_test.index, "zone_id"],
    "actual_occupancy":       y_test.values,
    "predicted_occupancy":    y_pred,
    "congestion_probability": congestion_probs,
    "expected_load_kwh":      y_pred * ml_data.loc[X_test.index, "capacity"] * avg_kwh_per_pile,
    "residual":               y_test.values - y_pred
})

pred_df.to_csv(os.path.join(outputs_dir, "demand_prediction_results.csv"), index=False)
print("Saved demand_prediction_results.csv in outputs/ folder.")

# Generate and save pricing agent CSV
flat_df_sorted["predicted_occupancy"] = np.clip(
    demand_model.predict(flat_df_sorted[features].fillna(0)), 0.0, 1.0
)

# Run coordinate search simulation
episodes               = 40
current_peak_thresh    = 0.80
current_offpeak_thresh = 0.30
history                = []

def evaluate_policy(peak_thresh, offpeak_thresh):
    pred_occ = flat_df_sorted["predicted_occupancy"].values
    occ_rate = flat_df_sorted["occupancy_rate"].values
    capacity = flat_df_sorted["capacity"].values

    tariffs = np.full_like(pred_occ, 15.0)
    peak_mask = pred_occ > peak_thresh
    offpeak_mask = pred_occ < offpeak_thresh

    tariffs[peak_mask] = 15.0 * (1.0 + 0.5 * (pred_occ[peak_mask] - peak_thresh) / (1.0 - peak_thresh))
    tariffs[offpeak_mask] = 15.0 * (1.0 - 0.3 * (offpeak_thresh - pred_occ[offpeak_mask]) / offpeak_thresh)

    pct_chg  = (tariffs - 15.0) / 15.0
    elas     = np.where(pct_chg > 0, -0.10, -0.85)
    occ_post = np.clip(occ_rate * (1.0 + elas * pct_chg), 0.0, 1.0)

    pk_mask = pred_occ > 0.80
    op_mask = pred_occ < 0.30
    red     = np.clip(occ_rate - occ_post, 0.0, 1.0)
    n_op    = op_mask.sum()
    if n_op > 0:
        redir    = red[pk_mask].sum() * 0.45 / n_op
        occ_post = np.where(op_mask, np.clip(occ_post + redir, 0.0, 1.0), occ_post)

    rev_base = (occ_rate * capacity * 15.0).sum()
    rev_dyn  = (occ_post * capacity * tariffs).sum()
    rev_gain = (rev_dyn - rev_base) / rev_base * 100.0

    q_base = flat_df_sorted["queue_length_proxy"].sum()
    q_dyn  = np.where(occ_post > 0.85, (occ_post - 0.85) * capacity * 1.5, 0.0).sum()
    q_red  = (q_base - q_dyn) / q_base * 100.0 if q_base > 0 else 0.0

    kwh_dyn = (occ_post * capacity).sum()
    p_eff   = rev_dyn / kwh_dyn if kwh_dyn > 0 else 0.0
    reward = rev_gain + 0.10 * q_red
    return reward, rev_gain, q_red, p_eff

for ep in range(1, episodes + 1):
    reward, rev_gain, q_red, p_eff = evaluate_policy(current_peak_thresh, current_offpeak_thresh)
    history.append({
        "episode": ep,
        "peak_threshold": current_peak_thresh,
        "offpeak_threshold": current_offpeak_thresh,
        "revenue_gain_pct": rev_gain,
        "queue_reduction_pct": q_red,
        "avg_waiting_time_reduction_pct": q_red,
        "pricing_efficiency": p_eff
    })
    best_r, best_p, best_op = reward, current_peak_thresh, current_offpeak_thresh
    for dp in [-0.015, 0.0, 0.015]:
        for dop in [-0.015, 0.0, 0.015]:
            cp  = np.clip(current_peak_thresh    + dp,  0.30, 0.90)
            cop = np.clip(current_offpeak_thresh + dop, 0.05, 0.35)
            r, _, _, _ = evaluate_policy(cp, cop)
            if r > best_r:
                best_r, best_p, best_op = r, cp, cop
    current_peak_thresh, current_offpeak_thresh = best_p, best_op

history_df = pd.DataFrame(history)
history_df.to_csv(os.path.join(outputs_dir, "pricing_agent_performance.csv"), index=False)
print("Saved pricing_agent_performance.csv in outputs/ folder.")

print("Writing README.txt...")

# Write README.txt
readme_content = """================================================================================
PROJECT SUBMISSION README
================================================================================

PROJECT TITLE:
Agentic AI-Based Dynamic Tariff Optimization for EV Charging Networks

ORGANIZATION:
Open Project 2026 — Society of Business, IIT Roorkee

--------------------------------------------------------------------------------
1. PROJECT OVERVIEW
--------------------------------------------------------------------------------
This project designs and evaluates a three-agent optimization pipeline to implement 
dynamic pricing in EV charging networks. The system transitions charging operators 
from static pricing (flat Rs.15/kWh baseline) to adaptive tariffs based on high-resolution 
occupancy predictions, optimizing both network revenue and grid demand balances.

The agent pipeline consists of:
1. Demand Prediction Agent: Forecasts short-term pile occupancy utilizing a 
   Gradient Boosting Regressor (R^2 = 0.9947, RMSE = 0.0129).
2. Tariff Pricing Agent: Simulates dynamic pricing (linear surcharges up to +50% 
   during congestion, linear discounts up to -30% during low demand) and incorporates 
   an asymmetric customer elasticity model (inelastic peaks, elastic valleys).
3. Monitoring & Learning Agent: Automatically optimizes surcharge/discount 
   thresholds over successive operational episodes via coordinate ascent.

--------------------------------------------------------------------------------
2. DIRECTORY STRUCTURE
--------------------------------------------------------------------------------
Google_Drive_Submission/
├── EV_Tariff_optimization_24124005.ipynb  <-- Main project Jupyter Notebook
├── README.txt                             <-- This project summary file
├── graphs/                                <-- Folder containing all 15 key charts
│   ├── 1_cbd_vs_res_demand.png
│   ├── 2_occupancy_distribution.png
│   ├── 3_ACN_station_utilization.png
│   ├── 4_ACN_session_efficiency.png
│   ├── 5_occupancy_heatmap.png
│   ├── 6_fleet_vs_public.png
│   ├── 7_weekly_longrun_trend.png
│   ├── 8_demand_prediction_diagnostics.png
│   ├── 9_peak_shaving_impact.png
│   ├── 10_dynamic_tariff_vs_grid.png
│   ├── 11_threshold_optimization_curve.png
│   ├── 12_pricing_efficiency_score.png
│   ├── 13_threshold_convergence.png
│   ├── 14_kpi_comparison.png
│   └── 15_revenue_gain_distribution.png
└── outputs/                                <-- Folder containing generated CSV files
    ├── demand_prediction_results.csv       <-- Test predictions, expected load, & residuals
    └── pricing_agent_performance.csv       <-- Learning history across the 40 episodes

--------------------------------------------------------------------------------
3. GRAPHS & PLOTS DESCRIPTION
--------------------------------------------------------------------------------
* 1_cbd_vs_res_demand.png: Traces hourly diurnal occupancy for CBD vs Residential 
  zones and contrasts Weekdays vs Weekend demand profiles.
* 2_occupancy_distribution.png: Boxplots showing occupancy rate dispersion across 
  Peak, Shoulder, and Off-Peak times.
* 3_ACN_station_utilization.png: Horizon bar charts showing top 20 station utilization 
  rates and bubble scatters relating session counts, average kWh, and utilization.
* 4_ACN_session_efficiency.png: Histograms of kWh delivered by period and scatters 
  of session duration vs. energy delivered.
* 5_occupancy_heatmap.png: 2D heatmap showing average occupancy by Hour of Day x Day of Week.
* 6_fleet_vs_public.png: Highlights usage signatures (volumes, diurnal times, draws) 
  separating Fleet/Repeat users from casual public parkers.
* 7_weekly_longrun_trend.png: Displays long-run demand aggregates and peak slot congestion.
* 8_demand_prediction_diagnostics.png: Compares actual vs. predicted occupancy and 
  outlines the Gradient Boosting Regressor feature importances.
* 9_peak_shaving_impact.png: Demonstrates peak-shaving and valley-filling on a CBD zone 
  under flat baseline vs dynamic pricing.
* 10_dynamic_tariff_vs_grid.png: Compares average dynamic tariffs with Time-of-Day grid costs.
* 11_threshold_optimization_curve.png: Tracks revenue gains and queue length reductions 
  across 40 coordinate ascent optimization episodes.
* 12_pricing_efficiency_score.png: Shows pricing efficiency (revenue per unit of energy) 
  increasing across episodes.
* 13_threshold_convergence.png: Details peak/off-peak threshold variables converging.
* 14_kpi_comparison.png: Side-by-side bar comparison of Revenue, Utilization, and Congestion.
* 15_revenue_gain_distribution.png: Histogram of revenue gains achieved across training.

--------------------------------------------------------------------------------
4. OPTIMIZED PERFORMANCE SUMMARY (EPISODE 40)
--------------------------------------------------------------------------------
* Revenue Gain: +6.75% operator revenue increase.
* Congestion & Queue reduction: -53.77% wait-line reduction during peak hours.
* Off-Peak Uplift: +8.23% increase in session utilization during discount hours.
* Net Customer Response Rate: +2.95% overall volume shift.
* Pricing Efficiency Yield: ₹16.126/kWh (vs ₹15.00 flat baseline).
* Optimal Threshold Parameters:
  - Peak threshold: 0.300
  - Off-peak threshold: 0.050

================================================================================
"""

with open(os.path.join(submission_dir, "README.txt"), "w", encoding="utf-8") as f:
    f.write(readme_content.strip() + "\n")

print("README.txt written successfully.")
print("Google Drive Submission folder is completely structured and ready!")
