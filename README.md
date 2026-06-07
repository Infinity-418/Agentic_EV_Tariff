# Agentic AI-Based Dynamic Tariff Optimization for EV Charging Networks

**Open Project 2026 — Society of Business, IIT Roorkee**

This repository contains an agentic AI framework designed to transition EV charging networks from static pricing (flat ₹15/kWh baseline) to adaptive tariffs based on high-resolution occupancy forecasts. By modeling asymmetric customer elasticity, the system shaves peak-hour congestion, fills off-peak valleys, and increases charging operator revenues.

---

## 📂 Repository Structure

*   `EV_Tariff_optimization_24124005.ipynb` - Main Jupyter Notebook containing the full data pipeline, ML models, and simulation loops.
*   `README.md` - Project overview, agentic architecture, metrics, and key results.
*   `plots/` - High-resolution visualizations generated during EDA, model validation, and simulation phases.
*   `outputs/` - Generated data deliverables:
    *   `demand_prediction_results.csv` - Next-interval occupancy predictions, expected loads, and residuals.
    *   `pricing_agent_performance.csv` - Epizodic logs of threshold coordinates and revenue yields.
*   `save_plots.py` - Python script to download datasets, train models, and export figures.
*   `generate_deck.py` - Programmatically constructs slide decks with embedded charts.
*   `patch_pdf_fitz.py` - Vector PDF utility to cover watermarks directly on the PDF graphics layer.

---

## ⚙️ Preprocessing & Key Formulations

1.  **Dataset Alignment**: Session-level driver behaviors are extracted from **Caltech/JPL ACN-Data**, while temporal occupancy signals are modeled from **Shenzhen UrbanEV (ST-EVCDP)**.
2.  **Queue Length Proxy**: Modeled when occupancy rate exceeds 85% to proxy driver wait times:
    $$\text{Queue Length} = \max\left(0, (\text{Occupancy Rate} - 0.85) \times \text{Capacity} \times 1.5\right)$$
3.  **Grid Time-of-Day (ToD) Costs**: Reflected Indian utility cost tiers:
    *   *Peak (₹10.0/kWh)*: 09:00-12:00, 18:00-21:00
    *   *Off-Peak (₹4.0/kWh)*: 00:00-06:00
    *   *Shoulder (₹7.0/kWh)*: All other hours

---

## 🤖 Agentic Pipeline Architecture

```
                 +-----------------------------+
                 |    ACN & UrbanEV Data       |
                 +--------------+--------------+
                                |
                                v
                 +--------------+--------------+
                 |   Agent 1: Demand Predict   |
                 +--------------+--------------+
                                | Predicted Occupancy
                                v
                 +--------------+--------------+
                 |    Agent 2: Tariff Pricing  | <----+
                 +--------------+--------------+      |
                                |                     | Threshold
                                v                     | Coordinates
                 +--------------+--------------+      |
                 |   Agent 3: Monitor & Learn  | -----+
                 +-----------------------------+
```

### 1. Demand Prediction Agent
Trains a **Gradient Boosting Regressor** (GBR) on historical lags (5m, 15m, 30m, 60m), rolling means, and grid cost features to forecast next-interval occupancy and outputs a sigmoid-scaled congestion probability.
*   **RMSE**: `0.0129`
*   **MAE**: `0.0048`
*   **R² Score**: `0.9947`

### 2. Tariff Pricing Agent
Maps predicted occupancy to dynamic price curves (surcharges up to +50% during congestion; discounts down to -30% during low demand). Incorporates asymmetric price elasticity:
*   *Surcharges*: $\epsilon = -0.10$ (Inelastic peak demand represents captive users).
*   *Discounts*: $\epsilon = -0.85$ (Elastic valley demand represents discretionary top-ups).
Redirects 45% of peak-shaved load to off-peak valley slots (valley filling).

### 3. Monitoring & Learning Agent
Runs a daily feedback loop over 40 episodes, executing coordinate ascent to tune surcharge/discount thresholds and maximize a joint reward function:
$$\text{Reward} = \text{Revenue Gain \%} + 0.10 \times \text{Queue Reduction \%}$$

---

## 📈 Key Results (Episode 40)

*   **Total Revenue Gain**: **+6.75%** overall yield increase (yields ₹16.126/kWh vs ₹15.00 flat baseline).
*   **Congestion & Wait Lines**: **-53.77%** reduction in peak-hour queue length.
*   **Off-Peak Uplift**: **+8.23%** increase in charging slots filled during discount valleys.
*   **Optimal Threshold Coordinates**:
    *   *Peak Threshold*: Converges to `0.300` (Lower bound; captures broad shoulder peaks under inelastic demand).
    *   *Off-Peak Threshold*: Converges to `0.050` (Shrinks discount slots to protect margins).
