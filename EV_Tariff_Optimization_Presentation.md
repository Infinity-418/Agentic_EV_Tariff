# Presentation Outline: Agentic AI-Based Dynamic Tariff Optimization for EV Charging Networks

**Open Project 2026 — Society of Business, IIT Roorkee**

This document details the structure, visual layouts, slide copy, and speaker notes for the 7 presentation slides (plus Cover and Appendix) designed for project verification.

---

## Slide 0: Title Slide (Dark Theme)

### Slide Content:
*   **Main Title**: Agentic AI-Based Dynamic Tariff Optimization for EV Charging Networks
*   **Subtitle**: Using Large-Scale Charging Session Data (Caltech/JPL & UrbanEV)
*   **Details**: Open Project 2026 — Society of Business, IIT Roorkee
*   **Prepared by**: [Insert Name] / Roll Number: [Insert Roll Number]

---

## Slide 1: Data Landscape & Preprocessing (Light Theme)

### Slide Content:
*   **Data Sources**:
    *   **ACN-Data (Caltech/JPL)**: 14,199 parsed charging sessions containing user inputs (minutes available, energy requested), connection/disconnection logs, and actual energy delivered (kWh).
    *   **UrbanEV (Shenzhen)**: 2,133,833 entries across 24,798 charging piles in 5-minute intervals, capturing fine-grained occupancy rates.
*   **Geographical Alignment Assumption**: Datasets are geographically disjoint and cannot be joined row-by-row. ACN supplies session behavior profiles (such as charging/session duration ratios), while UrbanEV supplies time-series occupancy signals for ML training.
*   **Feature Engineering & Proxies**:
    *   *Queue Length Proxy*: Computed when occupancy > 85%: $\text{Queue} = (\text{Occupancy Rate} - 0.85) \times \text{Capacity} \times 1.5$.
    *   *Grid Cost Tiers*: Diurnal ToD pricing: ₹4 off-peak (0-6h), ₹7 shoulder, ₹10 peak (9-12h, 18-21h).
    *   *Duration Cap*: Outliers in session duration (above 99th percentile) capped to prevent idle charging distortions.
*   **Missing Value Handling**: Drop rows with zero or negative durations; impute done-charging time as disconnect time (conservative estimate).

### Speaker Notes:
> "To build a realistic simulation, we use two massive real-world datasets: ACN-Data from Caltech/JPL for station-level session behavior, and UrbanEV from Shenzhen for high-resolution occupancy time-series. Because these are from different regions, we use them complementarily. We normalize occupancy rates to scale capacity differences and engineer a queue length proxy to model customer wait times when utilization exceeds 85%. Additionally, we structure a three-tier Time-of-Day grid cost model to evaluate procurement costs, replicating standard Indian utility pricing structures."

---

## Slide 2: Key EDA Findings & Demand Behavior Insights (Light Theme)

### Slide Content:
*   **CBD vs. Residential Diurnal Patterns**: CBD zones show sharp, high occupancy spikes during working hours (9:00 - 17:00), frequently exceeding the 80% congestion threshold. Residential zones show flatter, evening-biased demand.
*   **Weekday vs. Weekend Signatures**: Weekday demand has clear commute peaks, while weekend demand is evenly distributed and lower on average.
*   **User Type Segmentations**:
    *   *Fleet/Repeat Users* (users with >5 sessions): Exhibit consistent charging habits (often overnight) and draw significantly more energy per session (Avg: 14.05 kWh).
    *   *Public/Casual Users*: Peak during standard commute windows and draw smaller energy portions (Avg: 8.45 kWh).
*   **Long-Run Congestion Trend**: Weekly aggregated data reveals consistent baseline demand with regular, predictable congestion peaks.

### Visual Placement:
*   *Embedded Image*: `plots/1_cbd_vs_res_demand.png` (CBD vs Res + Weekday vs Weekend profiles) and `plots/6_fleet_vs_public.png` (Fleet vs Public usage details).

### Speaker Notes:
> "Our exploratory data analysis reveals distinct spatial and temporal demand structures. First, CBD zones experience heavy morning and afternoon peaks that exceed the 80% threshold, highlighting the need for surge pricing. Residential zones, on the other hand, show flat evening demand. Second, we identified a crucial user segment: repeat fleet users, who make up a small portion of users but draw almost twice as much energy per session compared to casual public users. These fleet users represent a highly predictable demand core that can be shifted using targeted discounts."

---

## Slide 3: Demand Prediction Agent (Light Theme)

### Slide Content:
*   **Model Architecture**: Gradient Boosting Regressor (GBR) trained on historical lag features. Capped tree depth prevents overfitting on highly autocorrelated lags.
*   **Feature Importance**: The 5-minute lag feature (`lag_1`) dominates model splits, confirming high time-series momentum. Time features (`hour`, `day_of_week`) and metadata (`is_cbd`) provide structural context.
*   **Key Model Performance Metrics**:
    *   **Root Mean Squared Error (RMSE)**: 0.0129 (Excellent precision in occupancy rate forecasts)
    *   **Mean Absolute Error (MAE)**: 0.0048
    *   **Coefficient of Determination ($R^2$ Score)**: 0.9947
*   **Agent Outputs**: Next-interval occupancy rate, sigmoid-scaled congestion probability, and expected charging load (kWh).
    *   *Total expected energy demand*: 83.767 GWh across the test set.

### Visual Placement:
*   *Embedded Image*: `plots/8_demand_prediction_diagnostics.png` (Scatter plot of Actual vs Forecasted + horizontal bar chart of GBR Feature Importances).

### Speaker Notes:
> "Our first agent is the Demand Prediction Agent. We implement a Gradient Boosting Regressor to predict occupancy rate in the next interval. A linear model would fail to capture the sharp boundaries and plateaus typical of CBD zones. The GBR achieves an R² score of 99.47% on the testing set. While the 5-minute lag feature dominates due to momentum, time variables provide critical structural boundaries. The agent translates these occupancy forecasts into a smooth, sigmoid-scaled congestion probability that our pricing agent uses to calculate tariffs."

---

## Slide 4: Tariff Pricing Agent & Elasticity Simulation (Light Theme)

### Slide Content:
*   **Pricing Logic (Rule-Based Curve)**:
    *   *Base Price*: ₹15.0/kWh flat rate.
    *   *Surge Premium ($>80\%$ occupancy)*: Linear surcharge up to +50% (₹22.50/kWh at 100% occupancy).
    *   *Off-Peak Discount ($<30\%$ occupancy)*: Linear discount up to -30% (₹10.50/kWh at 0% occupancy).
*   **Asymmetric Elasticity Model**:
    *   *Surcharges ($\epsilon = -0.10$)*: Peak charging is highly price-inelastic, representing captive drivers with immediate range needs.
    *   *Discounts ($\epsilon = -0.85$)*: Off-peak charging is highly price-elastic, representing flexible users responding to discount incentives.
*   **Valley Filling & Peak Shaving**:
    *   Pricing shaves the peak occupancy and redistributes 45% of this shed load into off-peak valley slots.

### Visual Placement:
*   *Embedded Image*: `plots/9_peak_shaving_impact.png` (Flat vs Dynamic occupancy comparison showing peak-shaving on a CBD zone) and `plots/10_dynamic_tariff_vs_grid.png` (Dynamic tariff vs grid cost).

### Speaker Notes:
> "The Tariff Pricing Agent maps predicted occupancy to dynamic rates, using ₹15/kWh as a baseline. The core innovation here is modeling asymmetric elasticity. During peak congestion, drivers are inelastic—they have low flexibility, so we charge a premium to capture revenue and manage queues. In off-peak valleys, drivers are highly elastic—they respond strongly to discounts. By lowering rates during low-occupancy periods, we encourage discretionary charging. Additionally, we simulate valley filling by redirecting 45% of peak-shaved demand to off-peak periods, smoothing the load curve."

---

## Slide 5: Monitoring & Learning Agent (Light Theme)

### Slide Content:
*   **The Feedback Optimization Loop**: Operates over successive episodes (daily intervals) to tune the pricing thresholds.
*   **Optimization Strategy**: Coordinate ascent search on thresholds ($\Delta = \pm 0.015$ per episode).
*   **Multi-Objective Reward Function**:
    $$\text{Reward} = \text{Revenue Gain \%} + 0.10 \times \text{Queue Reduction \%}$$
*   **Threshold Convergence Outcomes**:
    *   *Peak Threshold*: Converges from $0.800$ down to $0.300$ (lower bound).
    *   *Off-Peak Threshold*: Converges from $0.300$ down to $0.050$ (lower bound).
    *   *Rationale*: Under inelastic peak demand, expanding the surcharge range maximizes network revenue. Restricting discounts preserves margin, driving up the average tariff.

### Visual Placement:
*   *Embedded Image*: `plots/11_threshold_optimization_curve.png` (Revenue and Queue reduction vs Episode) and `plots/13_threshold_convergence.png` (Peak/Off-peak threshold convergence).

### Speaker Notes:
> "The Monitoring and Learning Agent provides the feedback loop. In a production system, this agent retrains models daily. Here, we optimize thresholds over the dataset using coordinate ascent to maximize a joint reward function that weights revenue gain and queue reduction. Over 40 episodes, we see the thresholds converge. The peak threshold moves to 0.300, and the off-peak threshold drops to 0.050. This tells us that to maximize revenue under inelastic demand, the system surcharges more frequently and discounts only under extreme underutilization."

---

## Slide 6: Business, Operational, & Policy Implications (Light Theme)

### Slide Content:
*   **Key KPI Outcomes (Baseline vs. Dynamic)**:
    *   **Revenue Gain**: **+6.75%** overall increase in revenue (from ₹15.00/kWh flat yield to ₹16.126/kWh average dynamic tariff).
    *   **Congestion & Queue Length**: **-53.77%** reduction in peak-hour wait lines.
    *   **Off-Peak Uplift**: **+8.23%** increase in charging activity during low-demand periods.
    *   **Customer Response Rate**: **+2.95%** net volume shift.
*   **Commercial Benefits**: Greater profitability without adding physical chargers.
*   **Operational Benefits**: Flattened load curve reduces local grid transformer strain, lowering peak thermal stress.
*   **Policy & Sustainability Alignment**: Promotes EV adoption by offering low-cost charging off-peak and reduces charger wait times.

### Visual Placement:
*   *Embedded Image*: `plots/14_kpi_comparison.png` (Comparison of Revenue, Utilization, and Congestion).

### Speaker Notes:
> "At episode 40, our dynamic pricing model delivers substantial business and operational benefits. We achieve a 6.75% increase in total revenue, driven by improved pricing efficiency of 16.126 Rupees per unit. Operationally, peak queues and waiting times drop by over 53%, while off-peak charging utilization rises by over 8%. This demonstrates that dynamic pricing can significantly reduce grid stress and congestion while simultaneously increasing operator revenue."

---

## Slide 7: Appendix, Limitations, & Future Scope (Light Theme)

### Slide Content:
*   **Limitations of the Offline Model**:
    *   *Geographic Disjoint*: Assuming US session behavior applies directly to Shenzhen spatial profiles is a necessary modelling compromise.
    *   *Static Simulation*: Coordinate ascent runs on static historical data. Live environments require online reinforcement learning (e.g., Q-learning or contextual bandits).
    *   *Elasticity Coefficients*: Elasticities ($\epsilon = -0.10, -0.85$) are assumed from literature and must be validated with live A/B tests.
*   **Future Scope**:
    *   *Co-located Datasets*: Validate on unified station logs containing co-located arrival, departure, and occupancy signals.
    *   *Renewable Integration*: Co-optimize charging tariffs with real-time solar/wind availability to maximize renewable utilization.
    *   *Vehicle-to-Grid (V2G)*: Extend agents to coordinate discharging tariffs during peak grid demand.

### Speaker Notes:
> "To conclude, we acknowledge key limitations. This is an offline simulation. In a live deployment, we would require co-located session and occupancy data from the same network and active A/B testing to verify elasticity parameters. For future scope, we recommend expanding the agents to incorporate renewable energy generation data, aligning charging discounts directly with solar and wind availability, and incorporating vehicle-to-grid capabilities to reward users who feed power back during peak demand."
