
PROJECT SUBMISSION README


PROJECT TITLE:
Agentic AI-Based Dynamic Tariff Optimization for EV Charging Networks

ORGANIZATION:
Open Project 2026 — Society of Business, IIT Roorkee


1. PROJECT OVERVIEW


This project explores how dynamic pricing can be used to improve the efficiency of
EV charging networks. Instead of using a fixed charging tariff of ₹15/kWh, the
system adjusts prices according to predicted charging demand and station occupancy.

The objective is to increase operator revenue while reducing congestion during
peak hours and improving utilization during low-demand periods.

The project is built around three interacting agents:

1. Demand Prediction Agent
   - Predicts short-term charging station occupancy.
   - Uses a Gradient Boosting Regressor model.
   - Achieved:
       • R² Score = 0.9947
       • RMSE = 0.0129

2. Tariff Pricing Agent
   - Dynamically adjusts charging prices based on predicted occupancy.
   - Applies surcharges during congestion and discounts during low demand.
   - Maximum surcharge: +50%
   - Maximum discount: -30%
   - Incorporates customer price sensitivity into pricing decisions.

3. Monitoring and Learning Agent
   - Tracks system performance over multiple episodes.
   - Continuously adjusts pricing thresholds.
   - Uses coordinate ascent optimization to improve overall performance.


2. DIRECTORY STRUCTURE

Google_Drive_Submission/
│
├── EV_Tariff_optimization_24124005.ipynb
│     Main project notebook
│
├── README.txt
│     Project summary and documentation
│
├── graphs/
│     Contains all generated visualizations
│
└── outputs/
      ├── demand_prediction_results.csv
      └── pricing_agent_performance.csv


3. VISUALIZATIONS


The notebook includes several visualizations that help analyze charging demand,
station utilization, model performance, and the impact of dynamic pricing.

Major plots include:

• Demand comparison across CBD and residential zones
• Occupancy distribution across different time periods
• Charging station utilization analysis
• Session efficiency and energy delivery trends
• Occupancy heatmaps
• Fleet versus public user behavior
• Weekly demand trends
• Demand prediction diagnostics
• Peak-shaving and valley-filling effects
• Dynamic tariff versus grid cost comparison
• Optimization learning curves
• Threshold convergence analysis
• KPI comparisons
• Revenue gain distribution

These visualizations provide insights into how dynamic pricing affects charging
behavior, congestion levels, and operator profitability.


4. RESULTS

After 40 optimization episodes, the final system achieved:

• Revenue Increase: +6.75%
• Queue Reduction: -53.77%
• Off-Peak Utilization Increase: +8.23%
• Customer Load Shift: +2.95%
• Pricing Efficiency: ₹16.126/kWh
• Baseline Tariff: ₹15.00/kWh

Optimal Parameters:

• Peak Threshold: 0.300
• Off-Peak Threshold: 0.050


5. CONCLUSION


The results show that dynamic tariff optimization can improve EV charging
network performance by increasing revenue, reducing congestion, and encouraging
better utilization of charging infrastructure. The agent-based framework
demonstrates how predictive analytics and adaptive pricing can be combined to
support more efficient charging operations.

