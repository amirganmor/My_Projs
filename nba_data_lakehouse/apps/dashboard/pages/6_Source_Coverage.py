"""Page: Source Coverage — how many players each source contributed."""
import streamlit as st
import plotly.express as px

from utils.data_loader import load_source_coverage

st.set_page_config(page_title="Source Coverage", layout="wide")
st.title("Source Coverage")
st.markdown("Coverage of player data across the 6 source families ingested into the lakehouse.")

df = load_source_coverage()

if df.empty:
    st.info("No coverage data available yet. Run the full pipeline first.")
    st.stop()

st.dataframe(df, use_container_width=True, hide_index=True)

if "source_name" in df.columns and "unique_players" in df.columns:
    fig = px.bar(
        df,
        x="source_name",
        y="unique_players",
        color="source_name",
        title="Unique Players per Source Family",
        labels={"source_name": "Source", "unique_players": "Unique Players"},
    )
    st.plotly_chart(fig, use_container_width=True)

if "total_records" in df.columns:
    fig2 = px.pie(
        df,
        names="source_name",
        values="total_records",
        title="Record Distribution by Source",
    )
    st.plotly_chart(fig2, use_container_width=True)

st.markdown("""
### Source Family Reference

| Source | Type | Description |
|--------|------|-------------|
| `nba_api` | API (cached JSON) | Official-style player stats, game logs, standings |
| `advanced_metrics` | File (CSV) | PER, TS%, USG%, OFF/DEF ratings |
| `shot_charts` | File (CSV/JSON) | Zone-level and raw shot data |
| `postgres_contracts` | SQL (PostgreSQL) | Salary and contract information |
| `postgres_injuries` | SQL (PostgreSQL) | Injury records |
| `mongo_profiles` | NoSQL (MongoDB) | Scouting reports and player narratives |
""")
