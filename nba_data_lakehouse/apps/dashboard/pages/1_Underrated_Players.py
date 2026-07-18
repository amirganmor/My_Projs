"""Page: Underrated Players — predicted value vs actual salary."""
import streamlit as st
import plotly.express as px

from utils.data_loader import load_underrated

st.set_page_config(page_title="Underrated Players", layout="wide")
st.title("Underrated Players")
st.markdown("Players whose predicted market value significantly exceeds their actual salary.")

df = load_underrated()

if df.empty:
    st.info("No scored data available yet. Run the full pipeline first.")
    st.stop()

# Display columns
display_cols = [c for c in [
    "rank", "PLAYER_NAME", "SEASON", "TEAM_ABBREVIATION",
    "PTS", "REB", "AST", "salary", "predicted_salary",
    "undervaluation_gap", "undervaluation_pct",
] if c in df.columns]

st.subheader("Top 50 Most Underrated Players")
st.dataframe(df[display_cols].head(50), use_container_width=True, hide_index=True)

# Chart
if "undervaluation_gap" in df.columns and "PLAYER_NAME" in df.columns:
    top_20 = df.head(20)
    fig = px.bar(
        top_20,
        x="PLAYER_NAME",
        y="undervaluation_gap",
        color="undervaluation_gap",
        color_continuous_scale="Greens",
        title="Top 20 Most Undervalued Players (Predicted - Actual Salary)",
        labels={"undervaluation_gap": "Undervaluation ($)", "PLAYER_NAME": "Player"},
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

# Scatter plot: predicted vs actual
if "salary" in df.columns and "predicted_salary" in df.columns:
    fig2 = px.scatter(
        df.head(200),
        x="salary",
        y="predicted_salary",
        hover_name="PLAYER_NAME" if "PLAYER_NAME" in df.columns else None,
        title="Predicted vs Actual Salary",
        labels={"salary": "Actual Salary ($)", "predicted_salary": "Predicted Salary ($)"},
    )
    fig2.add_shape(type="line", x0=0, y0=0, x1=df["salary"].max(), y1=df["salary"].max(),
                   line=dict(dash="dash", color="gray"))
    st.plotly_chart(fig2, use_container_width=True)
