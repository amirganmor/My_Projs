"""Page: Improvement Candidates — players likely to break out next season."""
import streamlit as st
import plotly.express as px

from utils.data_loader import load_improvement

st.set_page_config(page_title="Improvement Candidates", layout="wide")
st.title("Improvement Candidates")
st.markdown("Players most likely to significantly improve next season based on trajectory and context.")

df = load_improvement()

if df.empty:
    st.info("No scored data available yet. Run the full pipeline first.")
    st.stop()

display_cols = [c for c in [
    "rank", "PLAYER_NAME", "SEASON", "AGE",
    "PTS", "REB", "AST", "improvement_probability", "predicted_improved",
] if c in df.columns]

st.subheader("Top 50 Breakout Candidates")
st.dataframe(df[display_cols].head(50), use_container_width=True, hide_index=True)

if "improvement_probability" in df.columns and "PLAYER_NAME" in df.columns:
    top_25 = df.head(25)
    fig = px.bar(
        top_25,
        x="PLAYER_NAME",
        y="improvement_probability",
        color="improvement_probability",
        color_continuous_scale="YlOrRd",
        title="Top 25 Improvement Probability Scores",
        labels={"improvement_probability": "P(Improve)", "PLAYER_NAME": "Player"},
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

if "AGE" in df.columns and "improvement_probability" in df.columns:
    fig2 = px.scatter(
        df.head(200),
        x="AGE",
        y="improvement_probability",
        hover_name="PLAYER_NAME" if "PLAYER_NAME" in df.columns else None,
        size="PTS" if "PTS" in df.columns else None,
        title="Improvement Probability by Age",
        labels={"AGE": "Age", "improvement_probability": "P(Improve)"},
    )
    st.plotly_chart(fig2, use_container_width=True)
