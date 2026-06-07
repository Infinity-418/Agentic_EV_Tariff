import os
import zipfile
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

# Setup matplotlib styling
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 14,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'figure.titlesize': 16,
    'figure.dpi': 150
})

PRIMARY_GREEN   = "#0E4D44"
SECONDARY_GREEN = "#1AA384"
ACCENT_GREEN    = "#8FE8D2"
ALERT_RED       = "#C0392B"

workspace = "/Users/anubhav/Documents/EV_Tariff_Optimization"
os.makedirs(os.path.join(workspace, "plots"), exist_ok=True)

ACN_PATH    = os.path.join(workspace, "acndata_sessions.json")
URBANEV_ZIP = os.path.join(workspace, "ST-EVCDP-main.zip")

ACN_FILE_ID     = "1O0CUO_aE-4BiKWi9jekYR1zMYJ2ANMpK"
URBANEV_FILE_ID = "1dHh_stDTk3CrsUbI0Y8iqi6Nh6rK7pPN"

# Download files if they do not exist
try:
    import gdown
except ImportError:
    import subprocess
    subprocess.run(["pip", "install", "gdown", "-q"])
    import gdown

if not os.path.exists(ACN_PATH):
    print("Downloading acndata_sessions.json from Google Drive...")
    gdown.download(id=ACN_FILE_ID, output=ACN_PATH, quiet=False)

if not os.path.exists(URBANEV_ZIP):
    print("Downloading ST-EVCDP-main.zip from Google Drive...")
    gdown.download(id=URBANEV_FILE_ID, output=URBANEV_ZIP, quiet=False)

try:
    import ijson
except ImportError:
    import subprocess
    subprocess.run(["pip", "install", "ijson", "-q"])
    import ijson

# Grid cost helper
def get_grid_cost(dt):
    h = dt.hour
    if (9 <= h < 12) or (18 <= h < 21):
        return 10.0   # peak
    elif 0 <= h < 6:
        return 4.0    # off-peak
    else:
        return 7.0    # shoulder

print("Loading ACN sessions...")
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
        print("JSON truncated — proceeding with parsed sessions.")

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
acn_df["revenue_baseline"]  = acn_df["kwh_delivered"] * 15.0
acn_df["grid_cost_per_kwh"] = acn_df["connection_time"].apply(get_grid_cost)
acn_df["grid_cost_total"]   = acn_df["kwh_delivered"] * acn_df["grid_cost_per_kwh"]
acn_df["hour"]              = acn_df["connection_time"].dt.hour
acn_df["day_of_week"]       = acn_df["connection_time"].dt.dayofweek
acn_df["is_weekend"]        = acn_df["day_of_week"].isin([5, 6])

print("Loading UrbanEV ZIP...")
with zipfile.ZipFile(URBANEV_ZIP) as z:
    root = next((n.replace("occupancy.csv","") for n in z.namelist() if n.endswith("occupancy.csv")), None)
    if root is None:
        raise ValueError("occupancy.csv not found in ZIP.")
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
flat_df["occupancy_density"] = (flat_df["occupancy"] / flat_df["capacity"]).clip(0, 1)

print("Data loaded. Recreating plots...")

# 1. CBD vs Res Demand (Diurnal & Weekday/Weekend)
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
cbd_hourly = flat_df[flat_df["is_cbd"] == 1].groupby("hour")["occupancy_rate"].mean()
res_hourly = flat_df[flat_df["is_cbd"] == 0].groupby("hour")["occupancy_rate"].mean()
axes[0].plot(cbd_hourly.index, cbd_hourly.values, label="CBD zones",        color=PRIMARY_GREEN,   lw=2.5, marker='o', markersize=5)
axes[0].plot(res_hourly.index, res_hourly.values, label="Residential zones", color=SECONDARY_GREEN, lw=2.5, marker='s', markersize=5)
axes[0].axhspan(0.80, 1.0, alpha=0.07, color=ALERT_RED, label="Congestion zone (>80%)")
axes[0].set_title("Diurnal Occupancy: CBD vs Residential", fontweight="bold")
axes[0].set_xlabel("Hour of Day")
axes[0].set_ylabel("Avg Occupancy Rate")
axes[0].set_xticks(range(0, 24, 2))
axes[0].legend()

wkday = flat_df[flat_df["is_weekend"] == False].groupby("hour")["occupancy_rate"].mean()
wkend = flat_df[flat_df["is_weekend"] == True ].groupby("hour")["occupancy_rate"].mean()
axes[1].plot(wkday.index, wkday.values, label="Weekday", color=PRIMARY_GREEN,   lw=2.5)
axes[1].plot(wkend.index, wkend.values, label="Weekend", color=SECONDARY_GREEN, lw=2.5, linestyle="--")
axes[1].set_title("Weekday vs Weekend Demand", fontweight="bold")
axes[1].set_xlabel("Hour of Day")
axes[1].set_ylabel("Avg Occupancy Rate")
axes[1].set_xticks(range(0, 24, 2))
axes[1].legend()
plt.suptitle("UrbanEV Temporal Demand Profiles", fontsize=15, fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/1_cbd_vs_res_demand.png"), dpi=150)
plt.close()

# 2. Occupancy Rate by Period
flat_df["period"] = "Shoulder"
flat_df.loc[flat_df["hour"].isin([9,10,11,18,19,20]), "period"] = "Peak"
flat_df.loc[flat_df["hour"].isin([0,1,2,3,4,5]),      "period"] = "Off-Peak"
plt.figure(figsize=(8, 5))
period_order = ["Peak", "Shoulder", "Off-Peak"]
sns.boxplot(data=flat_df, x="period", y="occupancy_rate", order=period_order,
            hue="period", hue_order=period_order, legend=False,
            palette=[ALERT_RED, SECONDARY_GREEN, PRIMARY_GREEN])
plt.title("Occupancy Distribution by Operational Period", fontweight="bold")
plt.xlabel("Period")
plt.ylabel("Occupancy Rate")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/2_occupancy_distribution.png"), dpi=150)
plt.close()

# 3. ACN Station-Level Analysis
station_stats = acn_df.groupby("station_id").agg(
    avg_utilization=("charger_utilization_rate","mean"),
    std_utilization=("charger_utilization_rate","std"),
    session_count  =("session_id","count"),
    avg_kwh        =("kwh_delivered","mean")
).reset_index().sort_values("avg_utilization", ascending=False)
top20 = station_stats.head(20)

fig, axes = plt.subplots(1, 2, figsize=(16, 6))
colors_bar = [ALERT_RED if u >= 0.80 else PRIMARY_GREEN if u >= 0.40 else ACCENT_GREEN
              for u in top20["avg_utilization"]]
axes[0].barh(top20["station_id"][::-1], top20["avg_utilization"][::-1], color=colors_bar[::-1], height=0.6)
axes[0].axvline(0.80, color=ALERT_RED,   linestyle="--", lw=1.5, label="Surge threshold (80%)")
axes[0].axvline(0.30, color="steelblue", linestyle="--", lw=1.5, label="Discount threshold (30%)")
axes[0].set_title("Top 20 Stations — Avg Charger Utilization", fontweight="bold")
axes[0].set_xlabel("Avg Utilization Rate")
axes[0].set_ylabel("Station ID")
axes[0].legend(loc="lower right")

top30 = station_stats.head(30)
scatter = axes[1].scatter(
    top30["session_count"], top30["avg_kwh"],
    c=top30["avg_utilization"], cmap="RdYlGn",
    s=top30["session_count"] / top30["session_count"].max() * 300 + 40,
    alpha=0.85, edgecolors="white", linewidth=0.5
)
cbar = plt.colorbar(scatter, ax=axes[1])
cbar.set_label("Avg Utilization Rate", fontsize=10)
axes[1].set_title("Session Volume vs Avg kWh Delivered\n(bubble size = relative session volume)", fontweight="bold")
axes[1].set_xlabel("Session Count")
axes[1].set_ylabel("Avg kWh Delivered")
plt.suptitle("ACN Station-Level Analysis", fontsize=15, fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/3_ACN_station_utilization.png"), dpi=150)
plt.close()

# 4. ACN Session Efficiency Analysis
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
acn_df["tod_period"] = "Shoulder"
acn_df.loc[acn_df["hour"].isin([9,10,11,18,19,20]), "tod_period"] = "Peak"
acn_df.loc[acn_df["hour"].isin([0,1,2,3,4,5]),      "tod_period"] = "Off-Peak"
sns.histplot(data=acn_df, x="kwh_delivered", hue="tod_period",
             bins=40, kde=True, ax=axes[0],
             palette={"Peak": ALERT_RED, "Shoulder": SECONDARY_GREEN, "Off-Peak": PRIMARY_GREEN},
             alpha=0.55)
axes[0].set_title("kWh Delivered Distribution by Period", fontweight="bold")
axes[0].set_xlabel("kWh Delivered per Session")
axes[0].set_ylabel("Session Count")

sample = acn_df.sample(min(2000, len(acn_df)), random_state=42)
sc = axes[1].scatter(
    sample["session_duration_hours"], sample["kwh_delivered"],
    c=sample["charger_utilization_rate"], cmap="RdYlGn",
    alpha=0.4, s=15
)
cbar2 = plt.colorbar(sc, ax=axes[1])
cbar2.set_label("Charger Utilization Rate", fontsize=10)
axes[1].set_title("Session Duration vs kWh Delivered\n(color = utilization rate)", fontweight="bold")
axes[1].set_xlabel("Session Duration (hours)")
axes[1].set_ylabel("kWh Delivered")
plt.suptitle("ACN Session Efficiency Analysis", fontsize=15, fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/4_ACN_session_efficiency.png"), dpi=150)
plt.close()

# 5. Occupancy Heatmap
pivot = flat_df.groupby(["day_of_week", "hour"])["occupancy_rate"].mean().unstack()
day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
plt.figure(figsize=(14, 4))
sns.heatmap(pivot, cmap="RdYlGn_r", linewidths=0.3, linecolor="white",
            xticklabels=range(0,24), yticklabels=day_labels,
            cbar_kws={"label": "Avg Occupancy Rate"})
plt.title("Occupancy Rate Heatmap — Hour of Day × Day of Week", fontweight="bold")
plt.xlabel("Hour of Day")
plt.ylabel("Day of Week")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/5_occupancy_heatmap.png"), dpi=150)
plt.close()

# 6. Fleet vs Public
session_counts = acn_df.groupby("user_id")["session_id"].count()
fleet_users = session_counts[session_counts > 5].index
acn_df["user_type"] = np.where(acn_df["user_id"].isin(fleet_users), "Fleet/Repeat", "Public/Casual")

fig, axes = plt.subplots(1, 3, figsize=(16, 5))
type_counts = acn_df["user_type"].value_counts()
axes[0].bar(type_counts.index, type_counts.values,
            color=[PRIMARY_GREEN, SECONDARY_GREEN], width=0.5, edgecolor="white")
axes[0].set_title("Session Volume by User Type", fontweight="bold")
axes[0].set_ylabel("Session Count")
for bar, val in zip(axes[0].patches, type_counts.values):
    axes[0].text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.01,
                 f"{val:,}", ha="center", va="bottom", fontsize=10, fontweight="bold")

fleet_hourly  = acn_df[acn_df["user_type"] == "Fleet/Repeat"].groupby("hour")["charger_utilization_rate"].mean()
public_hourly = acn_df[acn_df["user_type"] == "Public/Casual"].groupby("hour")["charger_utilization_rate"].mean()
axes[1].plot(fleet_hourly.index,  fleet_hourly.values,  label="Fleet/Repeat",  color=PRIMARY_GREEN,   lw=2.5, marker="o", markersize=5)
axes[1].plot(public_hourly.index, public_hourly.values, label="Public/Casual", color=SECONDARY_GREEN, lw=2.5, marker="s", markersize=5)
axes[1].set_title("Diurnal Utilization: Fleet vs Public", fontweight="bold")
axes[1].set_xlabel("Hour of Day")
axes[1].set_ylabel("Avg Charger Utilization Rate")
axes[1].set_xticks(range(0, 24, 2))
axes[1].legend()

sns.boxplot(data=acn_df, x="user_type", y="kwh_delivered",
            hue="user_type", legend=False,
            palette={"Fleet/Repeat": PRIMARY_GREEN, "Public/Casual": SECONDARY_GREEN},
            ax=axes[2])
axes[2].set_title("kWh Delivered: Fleet vs Public", fontweight="bold")
axes[2].set_xlabel("User Type")
axes[2].set_ylabel("kWh Delivered per Session")
plt.suptitle("Fleet vs. Public Usage Signatures (ACN)", fontsize=15, fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/6_fleet_vs_public.png"), dpi=150)
plt.close()

# 7. Long Run Trend
flat_df["week"] = flat_df["timestamp"].dt.to_period("W").apply(lambda r: r.start_time)
weekly_trend = flat_df.groupby("week").agg(
    avg_occupancy=("occupancy_rate", "mean"),
    peak_occupancy=("occupancy_rate", lambda x: (x > 0.80).mean() * 100)
).reset_index()

fig, ax1 = plt.subplots(figsize=(12, 4))
ax1.plot(weekly_trend["week"], weekly_trend["avg_occupancy"],
         color=PRIMARY_GREEN, lw=2.5, marker="o", markersize=4, label="Avg Occupancy Rate")
ax1.fill_between(weekly_trend["week"], weekly_trend["avg_occupancy"],
                 alpha=0.12, color=PRIMARY_GREEN)
ax1.set_xlabel("Week")
ax1.set_ylabel("Avg Occupancy Rate", color=PRIMARY_GREEN)
ax1.tick_params(axis="y", labelcolor=PRIMARY_GREEN)
ax1.legend(loc="upper left")

ax2 = ax1.twinx()
ax2.bar(weekly_trend["week"], weekly_trend["peak_occupancy"],
        color=ALERT_RED, alpha=0.25, width=5, label="% Slots >80% (peak congestion)")
ax2.set_ylabel("% Peak Congested Slots", color=ALERT_RED)
ax2.tick_params(axis="y", labelcolor=ALERT_RED)
ax2.legend(loc="upper right")
plt.title("Long-Run Demand Trend — Weekly Aggregation (UrbanEV)", fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/7_weekly_longrun_trend.png"), dpi=150)
plt.close()

print("Training demand GBR model...")
# Feature engineering for ML
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

y_pred = np.clip(demand_model.predict(X_test), 0.0, 1.0)

# 8. GBR Model Diagnostics
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
axes[0].scatter(y_test.values[:400], y_pred[:400], alpha=0.45, color=PRIMARY_GREEN, s=20)
axes[0].plot([0,1],[0,1], "r--", lw=2, label="Perfect forecast")
axes[0].set_title("Actual vs Forecasted Occupancy", fontweight="bold")
axes[0].set_xlabel("Actual")
axes[0].set_ylabel("Predicted")
axes[0].legend()

importances = pd.Series(demand_model.feature_importances_, index=features).sort_values(ascending=True)
colors_fi   = [PRIMARY_GREEN if imp > 0.1 else SECONDARY_GREEN for imp in importances.values]
importances.plot(kind="barh", ax=axes[1], color=colors_fi)
axes[1].set_title("Feature Importances (GBR)", fontweight="bold")
axes[1].set_xlabel("Relative Importance")
plt.suptitle("Demand Prediction Agent — Model Diagnostics", fontsize=15, fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/8_demand_prediction_diagnostics.png"), dpi=150)
plt.close()

# 9. Dynamic Pricing Simulation and Peak Shaving Plot
flat_df_sorted["predicted_occupancy"] = np.clip(
    demand_model.predict(flat_df_sorted[features].fillna(0)), 0.0, 1.0
)
def get_dynamic_tariff(occ, base=15.0):
    if occ > 0.80:
        return base * (1.0 + 0.5 * (occ - 0.80) / 0.20)
    elif occ < 0.30:
        return base * (1.0 - 0.3 * (0.30 - occ) / 0.30)
    return base

flat_df_sorted["dynamic_tariff"] = flat_df_sorted["predicted_occupancy"].apply(get_dynamic_tariff)
flat_df_sorted["price_change_pct"] = (flat_df_sorted["dynamic_tariff"] - 15.0) / 15.0
elasticity_vec = np.where(flat_df_sorted["price_change_pct"] > 0, -0.10, -0.85)
flat_df_sorted["occupancy_post_pricing"] = np.clip(
    flat_df_sorted["occupancy_rate"] * (1.0 + elasticity_vec * flat_df_sorted["price_change_pct"]), 0.0, 1.0
)

is_peak    = flat_df_sorted["predicted_occupancy"] > 0.80
is_offpeak = flat_df_sorted["predicted_occupancy"] < 0.30
peak_reductions = np.clip(flat_df_sorted["occupancy_rate"] - flat_df_sorted["occupancy_post_pricing"], 0.0, 1.0)
n_offpeak = is_offpeak.sum()
if n_offpeak > 0:
    redir = (peak_reductions[is_peak].sum() * 0.45) / n_offpeak
    flat_df_sorted.loc[is_offpeak, "occupancy_post_pricing"] = np.clip(
        flat_df_sorted.loc[is_offpeak, "occupancy_post_pricing"] + redir, 0.0, 1.0
    )

# Calculate revenue columns
flat_df_sorted["revenue_baseline"] = flat_df_sorted["occupancy_rate"] * flat_df_sorted["capacity"] * 15.0
flat_df_sorted["revenue_dynamic"]  = flat_df_sorted["occupancy_post_pricing"] * flat_df_sorted["capacity"] * flat_df_sorted["dynamic_tariff"]

ex_zone = flat_df_sorted[flat_df_sorted["is_cbd"] == 1]["zone_id"].unique()[0]
ex_day  = flat_df_sorted["timestamp"].dt.date.unique()[1]
ex_data = flat_df_sorted[(flat_df_sorted["zone_id"] == ex_zone) &
                          (flat_df_sorted["timestamp"].dt.date == ex_day)]

plt.figure(figsize=(11, 5))
t_axis = ex_data["timestamp"].dt.hour + ex_data["timestamp"].dt.minute/60
plt.plot(t_axis, ex_data["occupancy_rate"],         label="Flat pricing (baseline)", color=ALERT_RED, lw=2)
plt.plot(t_axis, ex_data["occupancy_post_pricing"], label="Dynamic pricing (post)",  color=PRIMARY_GREEN, lw=2)
plt.fill_between(t_axis, 0.80, 1.0, color=ALERT_RED, alpha=0.07, label="Congestion zone")
plt.axhline(0.30, color="steelblue", linestyle=":", lw=1.5, label="Discount trigger (30%)")
plt.title(f"Peak-Shaving Impact — Zone {ex_zone}", fontweight="bold")
plt.xlabel("Hour of Day")
plt.ylabel("Occupancy Rate")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/9_peak_shaving_impact.png"), dpi=150)
plt.close()

# 10. Dynamic Tariff vs Grid Cost
fig, ax1 = plt.subplots(figsize=(11, 5))
hourly_tariff = flat_df_sorted.groupby("hour")["dynamic_tariff"].mean()
hourly_grid   = flat_df_sorted.groupby("hour")["grid_cost_kwh"].mean()
ax1.plot(hourly_tariff.index, hourly_tariff.values, color=PRIMARY_GREEN, lw=2.5, marker='o', label="Avg Dynamic Tariff")
ax1.axhline(15.0, color="gray", linestyle="--", lw=1.5, label="Flat baseline (₹15)")
ax1.set_xlabel("Hour of Day")
ax1.set_ylabel("Dynamic Tariff (₹/kWh)", color=PRIMARY_GREEN)
ax1.tick_params(axis='y', labelcolor=PRIMARY_GREEN)
ax1.legend(loc="upper left")

ax2 = ax1.twinx()
ax2.step(hourly_grid.index, hourly_grid.values, where="mid", color=ALERT_RED, lw=2, linestyle=":", label="Grid Cost (₹/kWh)")
ax2.set_ylabel("Grid Procurement Cost (₹/kWh)", color=ALERT_RED)
ax2.tick_params(axis='y', labelcolor=ALERT_RED)
ax2.legend(loc="upper right")
plt.title("Dynamic Tariff vs Grid Procurement Costs", fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/10_dynamic_tariff_vs_grid.png"), dpi=150)
plt.close()

# 11-15: Learning Feedback Loop Simulation
print("Simulating feedback loop...")
episodes               = 40
current_peak_thresh    = 0.80
current_offpeak_thresh = 0.30
history                = []

def evaluate_policy(peak_thresh, offpeak_thresh):
    pred_occ = flat_df_sorted["predicted_occupancy"].values
    occ_rate = flat_df_sorted["occupancy_rate"].values
    capacity = flat_df_sorted["capacity"].values

    # Vectorized tariff calculation
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
    avg_waiting_time_reduction = q_red
    history.append({
        "episode": ep,
        "peak_threshold": current_peak_thresh,
        "offpeak_threshold": current_offpeak_thresh,
        "revenue_gain_pct": rev_gain,
        "queue_reduction_pct": q_red,
        "avg_waiting_time_reduction_pct": avg_waiting_time_reduction,
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

# 11. Monitoring Agent - Threshold Optimization Curve
fig, ax1 = plt.subplots(figsize=(11, 5))
ax1.plot(history_df["episode"], history_df["revenue_gain_pct"],
         color=PRIMARY_GREEN, lw=2.5, marker='o', markersize=5, label="Revenue Gain %")
ax1.set_xlabel("Episode (threshold optimization step)")
ax1.set_ylabel("Revenue Gain % vs Flat Baseline", color=PRIMARY_GREEN)
ax1.tick_params(axis='y', labelcolor=PRIMARY_GREEN)
ax2 = ax1.twinx()
ax2.plot(history_df["episode"], history_df["queue_reduction_pct"],
         color=SECONDARY_GREEN, lw=2.5, marker='s', markersize=5, label="Queue Reduction %")
ax2.set_ylabel("Queue Length Reduction %", color=SECONDARY_GREEN)
ax2.tick_params(axis='y', labelcolor=SECONDARY_GREEN)
ax1.legend(loc="center left")
ax2.legend(loc="center right")
plt.title("Monitoring Agent — Threshold Optimization Curve", fontweight="bold")
fig.tight_layout()
plt.savefig(os.path.join(workspace, "plots/11_threshold_optimization_curve.png"), dpi=150)
plt.close()

# 12. Pricing Efficiency Score over episodes
plt.figure(figsize=(10, 4))
plt.plot(history_df["episode"], history_df["pricing_efficiency"],
         color=PRIMARY_GREEN, lw=2.5, marker='D', markersize=5)
plt.title("Pricing Efficiency Score (₹ Revenue per kWh-Equivalent) over Episodes", fontweight="bold")
plt.xlabel("Episode")
plt.ylabel("₹ / kWh-equivalent")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/12_pricing_efficiency_score.png"), dpi=150)
plt.close()

# 13. Threshold convergence
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(history_df["episode"], history_df["peak_threshold"],
        color=ALERT_RED, lw=2.5, marker='o', markersize=4, label="Peak Threshold")
ax.plot(history_df["episode"], history_df["offpeak_threshold"],
        color="steelblue", lw=2.5, marker='s', markersize=4, label="Off-Peak Threshold")
ax.set_xlabel("Episode")
ax.set_ylabel("Threshold Value")
ax.set_title("Threshold Convergence over Episodes", fontweight="bold")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/13_threshold_convergence.png"), dpi=150)
plt.close()

# 14. KPI comparison
before = [
    flat_df_sorted["revenue_baseline"].sum() / 1e6,
    flat_df_sorted["occupancy_rate"].mean() * 100,
    (flat_df_sorted["occupancy_rate"] > 0.80).mean() * 100
]
# Recalculate post optimization pricing outcomes
final_peak = history_df['peak_threshold'].iloc[-1]
final_offpeak = history_df['offpeak_threshold'].iloc[-1]

pred_occ = flat_df_sorted["predicted_occupancy"].values
occ_rate = flat_df_sorted["occupancy_rate"].values

# Vectorized tariff calculation
tariffs = np.full_like(pred_occ, 15.0)
peak_mask = pred_occ > final_peak
offpeak_mask = pred_occ < final_offpeak

tariffs[peak_mask] = 15.0 * (1.0 + 0.5 * (pred_occ[peak_mask] - final_peak) / (1.0 - final_peak))
tariffs[offpeak_mask] = 15.0 * (1.0 - 0.3 * (final_offpeak - pred_occ[offpeak_mask]) / final_offpeak)

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

cap      = flat_df_sorted["capacity"].values
rev_dyn  = (occ_post * cap * tariffs).sum()

after = [
    rev_dyn / 1e6,
    occ_post.mean() * 100,
    (occ_post > 0.80).mean() * 100
]
labels = ["Total Revenue\n(M ₹)", "Avg Utilization\n(%)", "Peak Congestion\n(% slots >80%)"]

fig, axes = plt.subplots(1, 3, figsize=(14, 5))
for i, ax in enumerate(axes):
    bars = ax.bar(["Flat Baseline", "Dynamic"], [before[i], after[i]],
                  color=["lightcoral", PRIMARY_GREEN], width=0.5, edgecolor="white")
    ax.set_title(labels[i], fontweight="bold")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Flat Baseline", "Dynamic"])
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h * 1.01, f"{h:.2f}",
                ha="center", va="bottom", fontsize=9, fontweight="bold")
plt.suptitle("KPI Comparison: Flat vs Dynamic Pricing", fontsize=15, fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/14_kpi_comparison.png"), dpi=150)
plt.close()

# 15. Revenue gain distribution
plt.figure(figsize=(8, 4))
plt.hist(history_df["revenue_gain_pct"], bins=15, color=PRIMARY_GREEN, edgecolor="white", alpha=0.85)
plt.axvline(history_df["revenue_gain_pct"].mean(), color=ALERT_RED, lw=2, linestyle="--",
            label=f"Mean: {history_df['revenue_gain_pct'].mean():.2f}%")
plt.title("Distribution of Revenue Gain % Across Episodes", fontweight="bold")
plt.xlabel("Revenue Gain %")
plt.ylabel("Episode Count")
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(workspace, "plots/15_revenue_gain_distribution.png"), dpi=150)
plt.close()

print("All plots saved successfully in the 'plots/' directory.")
