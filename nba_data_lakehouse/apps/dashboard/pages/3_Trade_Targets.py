"""Page: Trade Targets — composite-scored trade value rankings."""
import streamlit as st
import plotly.express as px

from utils.data_loader import load_trade_targets

st.set_page_config(page_title="Trade Targets", layout="wide")
st.title("Trade Target Rankings")
st.markdown("Players ranked by composite trade value: performance, contract efficiency, age/upside, durability, and scouting.")

df = load_trade_targets()

if df.empty:
    st.info("No scored data available yet. Run the full pipeline first.")
    st.stop()

display_cols = [c for c in [
    "rank", "PLAYER_NAME", "SEASON", "tier",
    "trade_target_score", "performance_score", "contract_efficiency",
    "age_upside_score", "durability_score", "salary",
] if c in df.columns]

# Filter by tier
if "tier" in df.columns:
    tiers = ["All"] + sorted(df["tier"].dropna().unique().tolist())
    selected = st.selectbox("Filter by Tier", tiers)
    if selected != "All":
        df = df[df["tier"] == selected]

st.subheader(f"Trade Targets ({len(df)} players)")
st.dataframe(df[display_cols].head(100), use_container_width=True, hide_index=True)

if "trade_target_score" in df.columns and "PLAYER_NAME" in df.columns:
    top_20 = df.head(20)
    fig = px.bar(
        top_20,
        x="PLAYER_NAME",
        y="trade_target_score",
        color="tier" if "tier" in top_20.columns else "trade_target_score",
        title="Top 20 Trade Targets by Composite Score",
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

# Component breakdown
score_cols = [c for c in ["performance_score_norm", "contract_efficiency_norm",
                          "age_upside_score_norm", "durability_score_norm",
                          "efficiency_score_norm"] if c in df.columns]
if score_cols and "PLAYER_NAME" in df.columns:
    top_10 = df.head(10)
    import pandas as pd
    melted = top_10.melt(id_vars=["PLAYER_NAME"], value_vars=score_cols,
                         var_name="Component", value_name="Score")
    fig2 = px.bar(melted, x="PLAYER_NAME", y="Score", color="Component",
                  barmode="stack", title="Top 10 — Score Component Breakdown")
    fig2.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig2, use_container_width=True)
